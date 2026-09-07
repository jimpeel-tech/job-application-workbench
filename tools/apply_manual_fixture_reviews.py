"""Apply independently reviewed fixture labels from a private manifest.

The manifest is intentionally stored beside the ignored private corpus so that
personal job-history data is not added to the public repository.  This helper
does not run JAW's extractor: every value must be supplied explicitly or be
selected from reviewed source-text lines.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

if __package__:
    from .fixture_review_schema import LIST_FIELDS, REVIEW_FIELDS
else:
    from fixture_review_schema import LIST_FIELDS, REVIEW_FIELDS


def _clean_source_line(line: str) -> str:
    return re.sub(
        r"^[\s\u00a0]*(?:(?:â€¢|•|Â·|·|[-*])|(?:\d+[.)]))\s*",
        "",
        line,
    ).strip()


def _line_values(lines: list[str], indexes: list[int]) -> list[str]:
    values: list[str] = []
    for number in indexes:
        if number < 1 or number > len(lines):
            raise ValueError(f"source line {number} is outside 1..{len(lines)}")
        value = _clean_source_line(lines[number - 1])
        if value and value not in values:
            values.append(value)
    return values


def _line_value(lines: list[str], index: int) -> str:
    values = _line_values(lines, [index])
    if not values:
        raise ValueError(f"source line {index} is blank")
    return values[0]


def apply_reviews(corpus_root: Path, manifest_path: Path) -> tuple[int, list[str]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reviews = manifest.get("reviews")
    if not isinstance(reviews, dict):
        raise ValueError("manifest must contain a 'reviews' object")

    output_root = corpus_root / "spreadsheet_approved"
    written: list[str] = []
    for fixture_id, review in reviews.items():
        source_path = corpus_root / f"{fixture_id}.txt"
        expected_path = output_root / f"{fixture_id}.expected.json"
        capture_path = output_root / f"{fixture_id}.capture.json"
        if not source_path.is_file() or not expected_path.is_file() or not capture_path.is_file():
            raise FileNotFoundError(f"missing source or expected file for {fixture_id}")

        source_text = source_path.read_text(encoding="utf-8-sig")
        lines = source_text.splitlines()
        capture = json.loads(capture_path.read_text(encoding="utf-8"))
        capture_values = [str(item.get("content", "")) for item in capture.get("captures", [])]
        if not capture_values:
            raise ValueError(f"{fixture_id}: capture document contains no captures")
        raw_description = "\n\n".join(capture_values)
        values: dict[str, Any] = dict(review.get("values", {}))
        for field, index in review.get("scalar_line_fields", {}).items():
            if field in LIST_FIELDS or field not in REVIEW_FIELDS:
                raise ValueError(f"{fixture_id}: {field} is not a scalar review field")
            values[field] = _line_value(lines, index)
        for field, indexes in review.get("line_fields", {}).items():
            if field not in LIST_FIELDS:
                raise ValueError(f"{fixture_id}: {field} is not a list field")
            values[field] = _line_values(lines, indexes)

        missing = [field for field in REVIEW_FIELDS if field not in values]
        extra = [field for field in values if field not in REVIEW_FIELDS]
        if missing or extra:
            raise ValueError(f"{fixture_id}: missing={missing or 'none'}, extra={extra or 'none'}")
        for field in LIST_FIELDS:
            if not isinstance(values[field], list) or not all(
                isinstance(item, str) and item.strip() for item in values[field]
            ):
                raise ValueError(f"{fixture_id}: {field} must be a list of strings")
        for field in set(REVIEW_FIELDS) - LIST_FIELDS:
            if not isinstance(values[field], str):
                raise ValueError(f"{fixture_id}: {field} must be a string")

        annotation = {
            "method": "independent_manual_review",
            "reviewer": review.get("reviewer", "Codex"),
            "reviewed_at": review.get("reviewed_at", "2026-08-12"),
            "source": "original fixture text",
        }
        if review.get("notes"):
            annotation["notes"] = review["notes"]

        result = {
            "fixture_id": fixture_id,
            **values,
            "raw_description": raw_description,
            "annotation": annotation,
        }
        expected_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(fixture_id)

    return len(written), written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("tests/fixtures/job_postings/private"),
    )
    args = parser.parse_args()
    count, fixture_ids = apply_reviews(args.corpus, args.manifest)
    print(f"Applied {count} independent reviews")
    for fixture_id in fixture_ids:
        print(f"  {fixture_id}")


if __name__ == "__main__":
    main()
