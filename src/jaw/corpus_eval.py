from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from .capture import extract_job_fields

SCALAR_FIELDS = (
    "company",
    "title",
    "job_id",
    "location",
    "remote_status",
    "employment_type",
    "pay_min",
    "pay_max",
    "currency",
    "pay_period",
    "education",
)
LIST_FIELDS = (
    "required_skills",
    "preferred_skills",
    "required_certifications",
    "experience_requirements",
    "responsibilities",
    "application_questions",
)


def normalize_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def normalize_number(value: Any) -> str:
    text = str(value).strip().replace(",", "").replace("$", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return normalize_text(value)
    return f"{float(match.group()):.4f}".rstrip("0").rstrip(".")


def normalized(field_name: str, value: Any) -> str:
    if field_name in {"pay_min", "pay_max"}:
        return normalize_number(value)
    return normalize_text(value)


def values_close(field_name: str, expected: Any, actual: Any) -> bool:
    wanted = normalized(field_name, expected)
    received = normalized(field_name, actual)
    if not wanted or not received:
        return wanted == received
    if wanted == received:
        return True
    if field_name in {"job_id", "pay_min", "pay_max", "currency", "pay_period"}:
        return False
    return (
        received in wanted
        or wanted in received
        or SequenceMatcher(None, wanted, received).ratio() >= 0.82
    )


def _list_match_count(wanted: set[str], received: set[str]) -> int:
    candidates: list[tuple[float, str, str]] = []
    for expected in wanted:
        expected_words = set(expected.split())
        for actual in received:
            actual_words = set(actual.split())
            overlap = len(expected_words & actual_words)
            containment = overlap / max(1, min(len(expected_words), len(actual_words)))
            sequence = SequenceMatcher(None, expected, actual).ratio()
            score = max(containment, sequence)
            single_term = len(expected_words) == 1 and expected in actual_words
            if expected == actual or single_term or (overlap >= 2 and score >= 0.62):
                candidates.append((score, expected, actual))
    matched_expected: set[str] = set()
    matched_actual: set[str] = set()
    for _, expected, actual in sorted(candidates, reverse=True):
        if expected not in matched_expected and actual not in matched_actual:
            matched_expected.add(expected)
            matched_actual.add(actual)
    return len(matched_expected)


@dataclass
class FieldScore:
    applicable: int = 0
    found: int = 0
    exact: int = 0
    close: int = 0
    expected_blank: int = 0
    false_positive: int = 0
    list_expected: int = 0
    list_matched: int = 0
    list_actual: int = 0

    def add(self, other: "FieldScore") -> None:
        for name in self.__dataclass_fields__:
            setattr(self, name, getattr(self, name) + getattr(other, name))

    def as_dict(self) -> dict[str, Any]:
        result = {
            name: getattr(self, name) for name in self.__dataclass_fields__
        }
        result.update({
            "found_rate": _ratio(self.found, self.applicable),
            "exact_rate": _ratio(self.exact, self.applicable),
            "close_rate": _ratio(self.close, self.applicable),
            "false_positive_rate": _ratio(
                self.false_positive, self.expected_blank
            ),
            "list_precision": _ratio(self.list_matched, self.list_actual),
            "list_recall": _ratio(self.list_matched, self.list_expected),
        })
        return result


@dataclass
class GroupScore:
    fixtures: int = 0
    fields: dict[str, FieldScore] = field(
        default_factory=lambda: defaultdict(FieldScore)
    )

    def add(self, field_name: str, score: FieldScore) -> None:
        self.fields[field_name].add(score)

    def as_dict(self) -> dict[str, Any]:
        total = FieldScore()
        for score in self.fields.values():
            total.add(score)
        return {
            "fixtures": self.fixtures,
            "summary": total.as_dict(),
            "fields": {
                name: score.as_dict()
                for name, score in sorted(self.fields.items())
            },
        }


def evaluate_corpus(root: Path) -> dict[str, Any]:
    overall = GroupScore()
    scenarios: dict[str, GroupScore] = defaultdict(GroupScore)
    sources: dict[str, GroupScore] = defaultdict(GroupScore)
    failures: list[dict[str, Any]] = []

    expected_paths = sorted(root.glob("*.expected.json"))
    for expected_path in expected_paths:
        fixture_id = expected_path.name.removesuffix(".expected.json")
        posting_path = root / f"{fixture_id}.txt"
        capture_path = root / f"{fixture_id}.capture.json"
        if not posting_path.exists():
            failures.append({
                "fixture_id": fixture_id,
                "field": "fixture",
                "expected": "posting text",
                "actual": "missing",
                "reason": "missing posting file",
            })
            continue

        expected = _read_json(expected_path)
        capture = _read_json(capture_path)
        manifest = capture.get("manifest", {})
        scenario = str(manifest.get("scenario") or "unknown")
        source = str(manifest.get("source_site") or "unknown")
        extraction = extract_job_fields(posting_path.read_text(encoding="utf-8"))
        actual = dict(extraction.get("fields", {}))
        actual["application_questions"] = extraction.get(
            "application_questions", []
        )

        groups = (overall, scenarios[scenario], sources[source])
        for group in groups:
            group.fixtures += 1

        for field_name in (*SCALAR_FIELDS, *LIST_FIELDS):
            wanted = expected.get(field_name, [] if field_name in LIST_FIELDS else "")
            received = actual.get(field_name, [] if field_name in LIST_FIELDS else "")
            score, reason = _score_field(field_name, wanted, received)
            for group in groups:
                group.add(field_name, score)
            if reason:
                failures.append({
                    "fixture_id": fixture_id,
                    "scenario": scenario,
                    "source": source,
                    "field": field_name,
                    "expected": wanted,
                    "actual": received,
                    "reason": reason,
                })

    return {
        "fixture_count": overall.fixtures,
        "overall": overall.as_dict(),
        "by_scenario": {
            name: score.as_dict() for name, score in sorted(scenarios.items())
        },
        "by_source": {
            name: score.as_dict() for name, score in sorted(sources.items())
        },
        "failures": failures,
    }


def render_markdown(report: dict[str, Any]) -> str:
    overall = report["overall"]["summary"]
    lines = [
        "# Smart Capture corpus baseline",
        "",
        f"Fixtures evaluated: **{report['fixture_count']}**",
        "",
        "## Overall",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Populated fields found | {_percent(overall['found_rate'])} |",
        f"| Exact field matches | {_percent(overall['exact_rate'])} |",
        f"| Close field matches | {_percent(overall['close_rate'])} |",
        f"| False positives on blank fields | {_percent(overall['false_positive_rate'])} |",
        f"| List-item precision | {_percent(overall['list_precision'])} |",
        f"| List-item recall | {_percent(overall['list_recall'])} |",
        "",
        "## By scenario",
        "",
        "| Scenario | Fixtures | Found | Close | False positive |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, group in report["by_scenario"].items():
        summary = group["summary"]
        lines.append(
            f"| {name} | {group['fixtures']} | {_percent(summary['found_rate'])} "
            f"| {_percent(summary['close_rate'])} "
            f"| {_percent(summary['false_positive_rate'])} |"
        )

    lines.extend([
        "",
        "## By source",
        "",
        "| Source | Fixtures | Found | Close | False positive |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for name, group in report["by_source"].items():
        summary = group["summary"]
        lines.append(
            f"| {name} | {group['fixtures']} | {_percent(summary['found_rate'])} "
            f"| {_percent(summary['close_rate'])} "
            f"| {_percent(summary['false_positive_rate'])} |"
        )

    lines.extend([
        "",
        "## Field results",
        "",
        "| Field | Expected | Found | Exact | Close | False positives |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for name, score in report["overall"]["fields"].items():
        lines.append(
            f"| {name} | {score['applicable']} | {_percent(score['found_rate'])} "
            f"| {_percent(score['exact_rate'])} | {_percent(score['close_rate'])} "
            f"| {score['false_positive']}/{score['expected_blank']} |"
        )

    failures = report.get("failures", [])
    lines.extend([
        "",
        f"## Mismatches ({len(failures)})",
        "",
        "The JSON report contains complete expected and actual values. This table is "
        "limited to the first 100 mismatches.",
        "",
        "| Fixture | Scenario | Source | Field | Reason | Expected | Actual |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for item in failures[:100]:
        lines.append(
            "| {fixture_id} | {scenario} | {source} | {field} | {reason} | "
            "{expected} | {actual} |".format(
                fixture_id=_cell(item.get("fixture_id", "")),
                scenario=_cell(item.get("scenario", "")),
                source=_cell(item.get("source", "")),
                field=_cell(item.get("field", "")),
                reason=_cell(item.get("reason", "")),
                expected=_cell(_display(item.get("expected", ""))),
                actual=_cell(_display(item.get("actual", ""))),
            )
        )
    return "\n".join(lines) + "\n"


def _score_field(
    field_name: str, expected: Any, actual: Any
) -> tuple[FieldScore, str]:
    if field_name in LIST_FIELDS:
        wanted = _normalized_list(expected)
        received = _normalized_list(actual)
        matched = _list_match_count(wanted, received)
        score = FieldScore()
        if wanted:
            score.applicable = 1
            score.found = int(bool(received))
            score.exact = int(wanted == received)
            score.close = int(matched == len(wanted))
            score.list_expected = len(wanted)
            score.list_actual = len(received)
            score.list_matched = matched
            if not received:
                return score, "missing list"
            if wanted != received:
                return score, "list mismatch"
            return score, ""
        score.expected_blank = 1
        score.false_positive = int(bool(received))
        score.list_actual = len(received)
        return score, "unexpected list" if received else ""

    wanted = normalized(field_name, expected)
    received = normalized(field_name, actual)
    score = FieldScore()
    if wanted:
        score.applicable = 1
        score.found = int(bool(received))
        score.exact = int(wanted == received)
        score.close = int(values_close(field_name, expected, actual))
        if not received:
            return score, "missing value"
        if not score.close:
            return score, "value mismatch"
        if not score.exact:
            return score, "close, not exact"
        return score, ""
    score.expected_blank = 1
    score.false_positive = int(bool(received))
    return score, "unexpected value" if received else ""


def _normalized_list(value: Any) -> set[str]:
    values: Iterable[Any]
    if isinstance(value, list):
        values = value
    elif value:
        values = str(value).splitlines()
    else:
        values = ()
    return {normalize_text(item) for item in values if normalize_text(item)}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def _display(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")[:180]
