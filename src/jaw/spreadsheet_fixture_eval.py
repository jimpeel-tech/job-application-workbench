from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .capture import extract_job_fields
from .capture_context import classify_capture_context, normalize_capture_for_parser
from .parser_resolution import resolve_parser_evidence
from .value_canonicalization import canonical_capture_value

_EXTRACTABLE_CONTEXTS = {
    "job_title",
    "company",
    "job_metadata",
    "job_description",
    "requirements",
    "responsibilities",
}
_SCALAR_FIELDS = (
    "company",
    "title",
    "job_id",
    "employment_type",
    "on_call",
    "travel",
    "clearance",
    "sponsorship",
    "application_deadline",
)


@dataclass(frozen=True)
class SpreadsheetFieldResult:
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


def evaluate_spreadsheet_corpus(root: Path) -> dict[str, Any]:
    """Evaluate archived spreadsheet fixtures without rewriting their reviewed schema.

    These fixtures reconstruct company/title/full-description captures from historic
    applied-job rows. They are useful for parser generalization, but they are not
    treated as authoritative tests of real capture-session morphology.
    """
    root = Path(root).resolve()
    fixtures: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    informational: list[dict[str, Any]] = []
    corpus_errors: list[dict[str, str]] = []
    field_totals: dict[str, dict[str, int]] = {}
    equivalent_passes = 0

    expected_files = sorted(root.glob("*.expected.json"))
    for expected_file in expected_files:
        fixture_id = expected_file.name.removesuffix(".expected.json")
        capture_file = root / f"{fixture_id}.capture.json"
        if not capture_file.exists():
            corpus_errors.append(
                {
                    "fixture_id": fixture_id,
                    "reason": f"missing capture file: {capture_file.name}",
                }
            )
            continue

        result = evaluate_spreadsheet_fixture(capture_file, expected_file)
        fixtures.append(result)
        for item in result["field_results"]:
            totals = field_totals.setdefault(item["field"], {"passed": 0, "failed": 0})
            totals["passed" if item["passed"] else "failed"] += 1
            if item["passed"] and item["reason"] == "safe_equivalent":
                equivalent_passes += 1
            if not item["passed"]:
                failures.append({"fixture_id": fixture_id, **item})
        for item in result["informational"]:
            informational.append({"fixture_id": fixture_id, **item})

    checks = sum(values["passed"] + values["failed"] for values in field_totals.values())
    passed = sum(values["passed"] for values in field_totals.values())
    return {
        "format": "jaw-spreadsheet-fixture-evaluation",
        "version": 2,
        "corpus_root": str(root),
        "fixture_count": len(fixtures),
        "expected_file_count": len(expected_files),
        "checks": checks,
        "passed": passed,
        "failed": checks - passed,
        "accuracy": round((passed / checks) * 100, 2) if checks else 0.0,
        "safe_equivalence_passes": equivalent_passes,
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
        "informational": informational,
        "informational_count": len(informational),
        "corpus_errors": corpus_errors,
    }


def evaluate_spreadsheet_fixture(
    capture_file: Path,
    expected_file: Path | None = None,
) -> dict[str, Any]:
    capture_file = Path(capture_file).resolve()
    if expected_file is None:
        expected_file = capture_file.with_name(
            capture_file.name.removesuffix(".capture.json") + ".expected.json"
        )
    expected = _read_json(Path(expected_file))
    capture_document = _read_json(capture_file)
    fixture_id = str(expected.get("fixture_id") or capture_file.name.removesuffix(".capture.json"))
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

    results: list[SpreadsheetFieldResult] = []
    informational: list[dict[str, Any]] = []

    for field in _SCALAR_FIELDS:
        if field not in expected:
            continue
        results.append(_compare_scalar(field, expected.get(field), actual_fields.get(field, [])))

    expected_pay = _expected_pay(expected)
    actual_pay = actual_fields.get("pay", [])
    results.append(_compare_scalar("pay", expected_pay, actual_pay))

    if "location" in expected:
        expected_location = str(expected.get("location") or "")
        if _comparable_location(expected_location):
            results.append(
                _compare_scalar("location", expected_location, actual_fields.get("location", []))
            )
        else:
            informational.append(
                {
                    "field": "location",
                    "expected": expected_location,
                    "actual": _display_actual(actual_fields.get("location", [])),
                    "reason": "rich_location_expectation_not_scored",
                }
            )

    if "remote_status" in expected:
        remote_expected = str(expected.get("remote_status") or "")
        accepted = _accepted_remote_values(remote_expected)
        actual_remote = actual_fields.get("remote_status", [])
        if accepted is None:
            informational.append(
                {
                    "field": "remote_status",
                    "expected": remote_expected,
                    "actual": _display_actual(actual_remote),
                    "reason": "rich_work_arrangement_expectation_not_scored",
                }
            )
        else:
            results.append(_compare_remote(remote_expected, accepted, actual_remote))

    return {
        "fixture_id": fixture_id,
        "capture_count": len(captures),
        "replay": replay,
        "actual_fields": actual_fields,
        "field_results": [item.as_dict() for item in results],
        "informational": informational,
        "passed": all(item.passed for item in results),
    }


def render_spreadsheet_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Spreadsheet Fixture Evaluation",
        "",
        f"- Fixtures: {report['fixture_count']}",
        f"- Checks: {report['checks']}",
        f"- Passed: {report['passed']}",
        f"- Failed: {report['failed']}",
        f"- Accuracy: {report['accuracy']:.2f}%",
        f"- Safe-equivalence passes: {report.get('safe_equivalence_passes', 0)}",
        f"- Informational rich fields not scored: {report['informational_count']}",
        f"- Corpus errors: {len(report['corpus_errors'])}",
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

    if report.get("corpus_errors"):
        lines.extend(["## Corpus errors", ""])
        for error in report["corpus_errors"]:
            lines.append(f"- {error['fixture_id']}: {error['reason']}")
        lines.append("")

    if report.get("informational"):
        lines.extend(
            [
                "## Informational rich expectations",
                "",
                "These values are preserved in the JSON report but excluded from the accuracy score",
                "because the archived expectation encodes multiple locations, conditional work",
                "arrangements, or other semantics in one narrative string.",
                "",
            ]
        )
        for item in report["informational"][:25]:
            lines.append(
                f"- {item['fixture_id']} · {item['field']}: "
                f"expected `{_display(item['expected'])}`, actual `{_display(item['actual'])}`"
            )
        if len(report["informational"]) > 25:
            lines.append(
                f"- … {len(report['informational']) - 25} additional informational values in JSON report"
            )

    return "\n".join(lines).rstrip() + "\n"


def _compare_scalar(field: str, expected: Any, actual_values: list[str]) -> SpreadsheetFieldResult:
    expected_text = str(expected or "").strip()
    actual = _display_actual(actual_values)
    if not expected_text:
        passed = not actual_values
        return SpreadsheetFieldResult(
            field,
            expected_text,
            actual,
            passed,
            "exact" if passed else "false_positive",
        )

    if len(actual_values) == 1:
        actual_text = str(actual_values[0])
        if _canonical_value(field, actual_text) == _canonical_value(field, expected_text):
            return SpreadsheetFieldResult(field, expected_text, actual, True, "exact")
        if _safe_equivalent(field, expected_text, actual_text):
            return SpreadsheetFieldResult(field, expected_text, actual, True, "safe_equivalent")

    return SpreadsheetFieldResult(
        field,
        expected_text,
        actual,
        False,
        "missing" if not actual_values else "value_mismatch",
    )


def _compare_remote(
    expected: str,
    accepted: set[str],
    actual_values: list[str],
) -> SpreadsheetFieldResult:
    actual = _display_actual(actual_values)
    if not expected.strip():
        passed = not actual_values
    else:
        actual_keys = {
            value
            for value in (_canonical_remote(str(item)) for item in actual_values)
            if value
        }
        passed = len(actual_keys) == 1 and next(iter(actual_keys)) in accepted
    return SpreadsheetFieldResult(
        "remote_status",
        expected,
        actual,
        passed,
        "exact" if passed else "missing" if not actual_values else "value_mismatch",
    )


def _expected_pay(expected: dict[str, Any]) -> str:
    low = str(expected.get("pay_min") or "").strip()
    high = str(expected.get("pay_max") or "").strip()
    currency = str(expected.get("currency") or "").strip().upper()
    period = str(expected.get("pay_period") or "").strip().casefold()
    if not low and not high:
        return ""
    amounts = [value for value in (low, high) if value]
    amount = (
        amounts[0]
        if len(amounts) == 1 or amounts[0] == amounts[-1]
        else f"{amounts[0]}–{amounts[-1]}"
    )
    prefix = "$" if currency == "USD" else f"{currency} " if currency else ""
    return f"{prefix}{amount}{f' per {period}' if period else ''}"


def _comparable_location(value: str) -> bool:
    text = " ".join(value.split()).strip()
    if not text:
        return True
    lowered = text.casefold()
    if ";" in text or len(text) > 100:
        return False
    if any(
        phrase in lowered
        for phrase in (
            "offices in",
            "employees",
            "hires",
            "reside in",
            "depending on",
            "except ",
            " or offices",
        )
    ):
        return False
    return True


def _accepted_remote_values(value: str) -> set[str] | None:
    text = " ".join(value.split()).strip()
    if not text:
        return {""}
    lowered = text.casefold()
    simple = {
        "remote": {"remote"},
        "fully remote": {"remote"},
        "hybrid": {"hybrid"},
        "on-site": {"on-site"},
        "onsite": {"on-site"},
        "in-person": {"on-site"},
        "hybrid/remote": {"hybrid", "remote"},
        "remote/hybrid": {"hybrid", "remote"},
        "remote or hybrid": {"hybrid", "remote"},
        "hybrid or remote": {"hybrid", "remote"},
        "flexible": {"flexible"},
    }
    if lowered in simple:
        return simple[lowered]
    return None


def _safe_equivalent(field: str, expected: str, actual: str) -> bool:
    if field == "pay":
        return _pay_equivalent_with_optional_period(expected, actual)
    if field == "location":
        return _canonical_location_equivalence(expected) == _canonical_location_equivalence(actual)
    return False


def _pay_equivalent_with_optional_period(expected: str, actual: str) -> bool:
    expected_key = canonical_capture_value("pay", expected)
    actual_key = canonical_capture_value("pay", actual)
    expected_parts = _pay_key_parts(expected_key)
    actual_parts = _pay_key_parts(actual_key)
    if not expected_parts or not actual_parts:
        return False
    if expected_parts["currency"] != actual_parts["currency"]:
        return False
    if expected_parts["amounts"] != actual_parts["amounts"]:
        return False
    expected_period = expected_parts["period"]
    actual_period = actual_parts["period"]
    return expected_period == actual_period or not expected_period or not actual_period


def _pay_key_parts(value: str) -> dict[str, str]:
    if not value.startswith("pay|"):
        return {}
    parts: dict[str, str] = {}
    for item in value.split("|")[1:]:
        key, separator, item_value = item.partition("=")
        if separator:
            parts[key] = item_value
    if not {"currency", "amounts", "period"}.issubset(parts):
        return {}
    return parts


def _canonical_location_equivalence(value: str) -> str:
    text = " ".join(str(value).split()).strip().casefold()
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r",\s*", ", ", text)
    text = re.sub(r"(?<=\w)\s*-\s*(?=\w)", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .,")

    country_aliases = {
        "us": "united states",
        "u.s": "united states",
        "u.s.": "united states",
        "usa": "united states",
        "u.s.a": "united states",
        "u.s.a.": "united states",
        "united states of america": "united states",
        "remote us": "united states",
        "remote u.s": "united states",
        "remote u.s.": "united states",
        "remote usa": "united states",
        "remote u.s.a": "united states",
        "remote u.s.a.": "united states",
        "remote united states": "united states",
        "remote united states of america": "united states",
    }
    if text in country_aliases:
        return country_aliases[text]

    remote_country = re.fullmatch(
        r"remote(?:\s*[-,/]\s*|\s+in\s+)(us|u\.s\.?|usa|u\.s\.a\.?|united states|united states of america)",
        text,
    )
    if remote_country:
        return "united states"
    return text


def _canonical_value(field: str, value: str) -> str:
    text = " ".join(str(value).split()).strip()
    if field == "pay":
        return canonical_capture_value(field, text)
    if field == "employment_type":
        lowered = text.casefold().replace("–", "-")
        lowered = re.sub(r"\bfull[- ]time\b", "full-time", lowered)
        lowered = re.sub(r"\bpart[- ]time\b", "part-time", lowered)
        lowered = re.sub(r"\bcontract[- ]to[- ]hire\b", "contract to hire", lowered)
        return lowered
    if field == "location":
        return _canonical_location_equivalence(text)
    return canonical_capture_value(field, text)


def _canonical_remote(value: str) -> str:
    lowered = " ".join(str(value).split()).casefold()
    if lowered in {"remote", "fully remote"}:
        return "remote"
    if lowered in {"hybrid"}:
        return "hybrid"
    if lowered in {"on-site", "onsite", "in-person"}:
        return "on-site"
    if lowered == "flexible":
        return "flexible"
    return lowered


def _display_actual(values: list[str]) -> Any:
    if not values:
        return []
    if len(values) == 1:
        return values[0]
    return values


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read fixture JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Fixture JSON must contain an object: {path}")
    return value


def _display(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


__all__ = [
    "evaluate_spreadsheet_corpus",
    "evaluate_spreadsheet_fixture",
    "render_spreadsheet_markdown",
]
