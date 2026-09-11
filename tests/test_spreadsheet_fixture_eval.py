from __future__ import annotations

import json

from jaw.spreadsheet_fixture_eval import (
    _compare_scalar,
    evaluate_spreadsheet_corpus,
    evaluate_spreadsheet_fixture,
)


def _write_fixture(tmp_path, fixture_id: str, expected: dict, captures: list[str]):
    capture_path = tmp_path / f"{fixture_id}.capture.json"
    expected_path = tmp_path / f"{fixture_id}.expected.json"
    capture_path.write_text(
        json.dumps(
            {
                "manifest": {
                    "format": "japa-capture-fixture",
                    "version": 1,
                    "fixture_id": fixture_id,
                    "scenario": "archived_description",
                },
                "captures": [
                    {"number": index, "content": content}
                    for index, content in enumerate(captures, start=1)
                ],
            }
        ),
        encoding="utf-8",
    )
    expected_path.write_text(json.dumps(expected), encoding="utf-8")
    return capture_path, expected_path


def test_archived_capture_fixture_scores_comparable_scalar_fields(tmp_path):
    fixture_id = "001-example-staff-devops-engineer"
    capture, expected = _write_fixture(
        tmp_path,
        fixture_id,
        {
            "fixture_id": fixture_id,
            "company": "Example Corp",
            "title": "Staff DevOps Engineer",
            "job_id": "JR64500",
            "location": "Remote - US",
            "remote_status": "Fully Remote",
            "employment_type": "Full-time",
            "pay_min": "150000",
            "pay_max": "200000",
            "currency": "USD",
            "pay_period": "year",
        },
        [
            "Example Corp",
            "Staff DevOps Engineer",
            (
                "remote type\nFully Remote\nlocations\nRemote - US\ntime type\nFull time\n"
                "job requisition id\nJR64500\nEstimated Pay Range\n$150,000 - $200,000 per year"
            ),
        ],
    )

    result = evaluate_spreadsheet_fixture(capture, expected)
    failures = [item for item in result["field_results"] if not item["passed"]]

    assert failures == []
    assert result["informational"] == []


def test_rich_remote_expectation_is_preserved_but_not_scored(tmp_path):
    fixture_id = "002-conditional-remote"
    capture, expected = _write_fixture(
        tmp_path,
        fixture_id,
        {
            "fixture_id": fixture_id,
            "company": "Example Corp",
            "title": "Principal Site Reliability Engineer",
            "job_id": "",
            "location": "United States",
            "remote_status": (
                "Remote; Minneapolis and Washington, D.C. hires must work in-office "
                "at least four days per week"
            ),
            "employment_type": "Full-time",
            "pay_min": "",
            "pay_max": "",
            "currency": "",
            "pay_period": "",
        },
        [
            "Example Corp",
            "Principal Site Reliability Engineer",
            (
                "Job Type: Full-time\nThis role is remote anywhere in the United States. "
                "Minneapolis hires must work in the office four days per week."
            ),
        ],
    )

    result = evaluate_spreadsheet_fixture(capture, expected)

    assert any(
        item["field"] == "remote_status"
        and item["reason"] == "rich_work_arrangement_expectation_not_scored"
        for item in result["informational"]
    )
    assert not any(
        item["field"] == "remote_status" for item in result["field_results"]
    )


def test_pay_period_can_be_omitted_from_archived_expectation():
    result = _compare_scalar(
        "pay",
        "$146000–190000",
        ["$146000–190000 per year"],
    )

    assert result.passed is True
    assert result.reason == "safe_equivalent"


def test_pay_currency_and_period_can_be_unspecified_in_archived_expectation():
    result = _compare_scalar(
        "pay",
        "175000–200000",
        ["$175000–200000 per year"],
    )

    assert result.passed is True
    assert result.reason == "safe_equivalent"


def test_conflicting_pay_period_is_not_treated_as_equivalent():
    result = _compare_scalar(
        "pay",
        "$60–98 per hour",
        ["$60–98 per year"],
    )

    assert result.passed is False
    assert result.reason == "value_mismatch"


def test_location_safe_equivalences_do_not_require_identity_fuzzing():
    us_result = _compare_scalar("location", "United States", ["Remote - US"])
    punctuation_result = _compare_scalar("location", "Customer site", ["Customer- site"])
    nyc_result = _compare_scalar("location", "New York City", ["New York City, NY"])

    assert us_result.passed is True
    assert punctuation_result.passed is True
    assert nyc_result.passed is True


def test_corpus_reports_missing_capture_pair_without_crashing(tmp_path):
    (tmp_path / "003-missing.capture.expected.json").write_text(
        json.dumps({"fixture_id": "003-missing.capture"}),
        encoding="utf-8",
    )

    report = evaluate_spreadsheet_corpus(tmp_path)

    assert report["fixture_count"] == 0
    assert report["expected_file_count"] == 1
    assert report["corpus_errors"] == [
        {
            "fixture_id": "003-missing.capture",
            "reason": "missing capture file: 003-missing.capture.capture.json",
        }
    ]
