from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .capture import extract_job_fields
from .capture_context import classify_capture_context, normalize_capture_for_parser
from .parser_resolution import resolve_parser_evidence
from .value_canonicalization import canonical_capture_value
from .work_arrangement_enrichment import analyze_enriched_work_arrangement

_EXTRACTABLE_CONTEXTS = {
    "job_title",
    "company",
    "job_metadata",
    "job_description",
    "requirements",
    "responsibilities",
}


@dataclass(frozen=True)
class FixtureFieldResult:
    field: str
    expected: Any
    actual: Any
    passed: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
            "passed": self.passed,
            "reason": self.reason,
        }


def evaluate_fixture_root(root: Path, baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    fixtures: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    field_totals: dict[str, dict[str, int]] = {}

    for fixture_file in sorted(root.rglob("fixture.json")):
        result = evaluate_fixture(fixture_file)
        fixtures.append(result)
        for item in result["field_results"]:
            totals = field_totals.setdefault(item["field"], {"passed": 0, "failed": 0})
            totals["passed" if item["passed"] else "failed"] += 1
            if not item["passed"]:
                failures.append(
                    {
                        "fixture_id": result["fixture_id"],
                        "domain": result.get("domain", ""),
                        **item,
                    }
                )
        for item in result.get("work_arrangement_results", []):
            key = f"work_arrangement.{item['field']}"
            totals = field_totals.setdefault(key, {"passed": 0, "failed": 0})
            totals["passed" if item["passed"] else "failed"] += 1
            if not item["passed"]:
                failures.append(
                    {
                        "fixture_id": result["fixture_id"],
                        "domain": result.get("domain", ""),
                        "field": key,
                        "expected": item["expected"],
                        "actual": item["actual"],
                        "passed": False,
                        "reason": item["reason"],
                    }
                )

    checks = sum(values["passed"] + values["failed"] for values in field_totals.values())
    passed = sum(values["passed"] for values in field_totals.values())
    report: dict[str, Any] = {
        "format": "jaw-smart-capture-evaluation",
        "version": 1,
        "corpus_root": str(root),
        "fixture_count": len(fixtures),
        "checks": checks,
        "passed": passed,
        "failed": checks - passed,
        "accuracy": round((passed / checks) * 100, 2) if checks else 0.0,
        "by_field": {
            field: {
                **values,
                "accuracy": round(
                    (values["passed"] / (values["passed"] + values["failed"])) * 100,
                    2,
                )
                if values["passed"] + values["failed"]
                else 0.0,
            }
            for field, values in sorted(field_totals.items())
        },
        "fixtures": fixtures,
        "failures": failures,
    }
    if baseline:
        report["comparison"] = compare_to_baseline(report, baseline)
    return report


def evaluate_fixture(fixture_file: Path) -> dict[str, Any]:
    fixture_file = Path(fixture_file).resolve()
    fixture = _read_json(fixture_file)
    fixture_dir = fixture_file.parent
    expected = _read_json(fixture_dir / "expected.json")

    capture_path = _resolve_source_path(
        fixture_dir,
        fixture.get("source", {}).get("captures"),
        "captures.json",
    )
    capture_document = _read_json(capture_path)
    captures = list(capture_document.get("captures", []))
    combined = "\n\n".join(
        str(item.get("content", "")).strip()
        for item in captures
        if str(item.get("content", "")).strip()
    )

    extractions: list[dict[str, Any]] = []
    replay: list[dict[str, Any]] = []
    previous: list[dict[str, Any]] = []
    for sequence, capture in enumerate(captures, start=1):
        raw = str(capture.get("content", ""))
        classification = classify_capture_context(raw, "job_capture", previous)
        normalized = normalize_capture_for_parser(raw, classification.content_type)
        extraction: dict[str, Any] = {}
        if classification.content_type in _EXTRACTABLE_CONTEXTS:
            extraction = extract_job_fields(normalized)
            extraction["capture_context"] = classification.content_type
            extractions.append(extraction)

        replay.append(
            {
                "sequence": sequence,
                "raw": raw,
                "content_type": classification.content_type,
                "confidence": classification.confidence,
                "reason": classification.reason,
                "normalized": normalized,
                "extraction": extraction,
            }
        )
        previous.append(
            {
                "content": raw,
                "content_type": classification.content_type,
                "classification_status": (
                    "pending" if classification.content_type == "unclassified" else "classified"
                ),
            }
        )

    resolution = resolve_parser_evidence(extractions, combined)
    actual_fields = {
        key: list(values)
        for key, values in resolution.values.items()
        if values
    }
    combined_fields = extract_job_fields(combined).get("fields", {})
    if combined_fields.get("job_id"):
        actual_fields["job_id"] = [str(combined_fields["job_id"])]

    field_results = [
        _compare_field(field, expected_value, actual_fields.get(field, []))
        for field, expected_value in expected.get("fields", {}).items()
    ]

    work_expected = expected.get("work_arrangement", {})
    work_actual = analyze_enriched_work_arrangement(combined)
    work_results = _compare_work_arrangement(work_expected, work_actual.as_dict())

    return {
        "fixture_id": str(fixture.get("fixture_id", fixture_dir.name)),
        "domain": str(fixture.get("domain", "")),
        "scenario": str(fixture.get("scenario", "")),
        "capture_count": len(captures),
        "replay": replay,
        "actual_fields": actual_fields,
        "field_results": [item.as_dict() for item in field_results],
        "work_arrangement": work_actual.as_dict(),
        "work_arrangement_results": work_results,
        "passed": all(item.passed for item in field_results)
        and all(item["passed"] for item in work_results),
    }


def compare_to_baseline(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    old = _result_index(baseline)
    new = _result_index(current)
    regressions: list[dict[str, str]] = []
    improvements: list[dict[str, str]] = []

    for key, passed in new.items():
        if key not in old:
            continue
        fixture_id, field = key
        if old[key] and not passed:
            regressions.append({"fixture_id": fixture_id, "field": field})
        elif not old[key] and passed:
            improvements.append({"fixture_id": fixture_id, "field": field})

    return {
        "baseline_accuracy": baseline.get("accuracy", 0.0),
        "current_accuracy": current.get("accuracy", 0.0),
        "regressions": regressions,
        "improvements": improvements,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Smart Capture Fixture Evaluation",
        "",
        f"- Fixtures: {report['fixture_count']}",
        f"- Checks: {report['checks']}",
        f"- Passed: {report['passed']}",
        f"- Failed: {report['failed']}",
        f"- Accuracy: {report['accuracy']:.2f}%",
        "",
        "## Field results",
        "",
        "| Field | Passed | Failed | Accuracy |",
        "| --- | ---: | ---: | ---: |",
    ]
    for field, values in report.get("by_field", {}).items():
        lines.append(
            f"| {field} | {values['passed']} | {values['failed']} | "
            f"{values['accuracy']:.2f}% |"
        )

    lines.extend(["", "## Failures", ""])
    failures = report.get("failures", [])
    if not failures:
        lines.append("No failures.")
    else:
        for failure in failures:
            lines.extend(
                [
                    f"### {failure['fixture_id']} · {failure['field']}",
                    "",
                    f"- Expected: `{_display(failure['expected'])}`",
                    f"- Actual: `{_display(failure['actual'])}`",
                    f"- Reason: `{failure['reason']}`",
                    "",
                ]
            )

    comparison = report.get("comparison")
    if comparison:
        lines.extend(
            [
                "## Baseline comparison",
                "",
                f"- Baseline accuracy: {float(comparison['baseline_accuracy']):.2f}%",
                f"- Current accuracy: {float(comparison['current_accuracy']):.2f}%",
                f"- Regressions: {len(comparison['regressions'])}",
                f"- Improvements: {len(comparison['improvements'])}",
                "",
            ]
        )
        if comparison["regressions"]:
            lines.append("### Regressions")
            lines.append("")
            for item in comparison["regressions"]:
                lines.append(f"- {item['fixture_id']} · {item['field']}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _compare_field(field: str, expected: Any, actual_values: list[str]) -> FixtureFieldResult:
    actual = actual_values[0] if len(actual_values) == 1 else actual_values
    if expected in ("", None, []):
        passed = not actual_values
        return FixtureFieldResult(
            field,
            expected,
            actual,
            passed,
            "exact" if passed else "false_positive",
        )

    if isinstance(expected, list):
        expected_keys = [canonical_capture_value(field, str(value)) for value in expected]
        actual_keys = [canonical_capture_value(field, str(value)) for value in actual_values]
        passed = expected_keys == actual_keys
    else:
        expected_key = canonical_capture_value(field, str(expected))
        actual_keys = [canonical_capture_value(field, str(value)) for value in actual_values]
        passed = len(actual_keys) == 1 and actual_keys[0] == expected_key

    return FixtureFieldResult(
        field,
        expected,
        actual,
        passed,
        "exact" if passed else "missing" if not actual_values else "value_mismatch",
    )


def _compare_work_arrangement(expected: dict[str, Any], actual: dict[str, Any]) -> list[dict[str, Any]]:
    if not expected:
        return []

    results: list[dict[str, Any]] = []
    for field in ("status", "conflict"):
        if field not in expected:
            continue
        passed = expected[field] == actual.get(field)
        results.append(
            {
                "field": field,
                "expected": expected[field],
                "actual": actual.get(field),
                "passed": passed,
                "reason": "exact" if passed else "value_mismatch",
            }
        )

    if "locations" in expected:
        expected_locations = {
            (str(item.get("value", "")).casefold(), str(item.get("relation", "")).casefold())
            for item in expected.get("locations", [])
        }
        actual_locations = {
            (str(item.get("location", "")).casefold(), str(item.get("location_relation", "")).casefold())
            for item in actual.get("evidence", [])
            if item.get("location")
        }
        passed = expected_locations <= actual_locations
        results.append(
            {
                "field": "locations",
                "expected": expected.get("locations", []),
                "actual": [
                    {"value": value, "relation": relation}
                    for value, relation in sorted(actual_locations)
                ],
                "passed": passed,
                "reason": "exact" if passed else "missing_or_wrong_relation",
            }
        )
    return results


def _resolve_source_path(fixture_dir: Path, configured: Any, fallback: str) -> Path:
    if configured:
        return (fixture_dir / str(configured)).resolve()
    return fixture_dir / fallback


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read fixture JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Fixture JSON must contain an object: {path}")
    return value


def _result_index(report: dict[str, Any]) -> dict[tuple[str, str], bool]:
    result: dict[tuple[str, str], bool] = {}
    for fixture in report.get("fixtures", []):
        fixture_id = str(fixture.get("fixture_id", ""))
        for item in fixture.get("field_results", []):
            result[(fixture_id, str(item.get("field", "")))] = bool(item.get("passed"))
        for item in fixture.get("work_arrangement_results", []):
            result[(fixture_id, f"work_arrangement.{item.get('field', '')}")] = bool(
                item.get("passed")
            )
    return result


def _display(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


__all__ = [
    "compare_to_baseline",
    "evaluate_fixture",
    "evaluate_fixture_root",
    "render_markdown",
]
