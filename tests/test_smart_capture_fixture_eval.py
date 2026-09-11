from __future__ import annotations

import json

from jaw.smart_capture_fixture_eval import (
    compare_to_baseline,
    evaluate_fixture_root,
    render_markdown,
)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_evaluator_replays_capture_order_and_reports_work_arrangement(tmp_path):
    fixture_dir = tmp_path / "golden" / "it" / "fixture-1"
    inbox_dir = tmp_path / "inbox" / "fixture-1"
    _write_json(
        fixture_dir / "fixture.json",
        {
            "fixture_id": "fixture-1",
            "domain": "it",
            "scenario": "remote_country_metadata",
            "source": {
                "captures": "../../../inbox/fixture-1/captures.json",
            },
        },
    )
    _write_json(
        inbox_dir / "captures.json",
        {
            "captures": [
                {"content": "Senior Site Reliability Engineer"},
                {"content": "Remote - Switzerland"},
            ]
        },
    )
    _write_json(
        fixture_dir / "expected.json",
        {
            "fields": {
                "title": "Senior Site Reliability Engineer",
                "location": "Switzerland",
                "remote_status": "Remote",
                "travel": "",
            },
            "work_arrangement": {
                "status": "Remote",
                "conflict": False,
                "locations": [
                    {"value": "Switzerland", "relation": "remote_eligibility"}
                ],
            },
        },
    )

    report = evaluate_fixture_root(tmp_path / "golden")

    assert report["fixture_count"] == 1
    assert report["failed"] == 0
    assert report["accuracy"] == 100.0
    fixture = report["fixtures"][0]
    assert fixture["replay"][1]["content_type"] == "job_metadata"
    assert fixture["replay"][1]["normalized"] == "Remote\nLocation: Switzerland"
    assert fixture["work_arrangement"]["location"] == "Switzerland"


def test_evaluator_reports_granular_field_failure(tmp_path):
    fixture_dir = tmp_path / "golden" / "general" / "fixture-2"
    _write_json(
        fixture_dir / "fixture.json",
        {"fixture_id": "fixture-2", "domain": "general"},
    )
    _write_json(
        fixture_dir / "captures.json",
        {"captures": [{"content": "Remote"}]},
    )
    _write_json(
        fixture_dir / "expected.json",
        {
            "fields": {"remote_status": "Hybrid"},
            "work_arrangement": {"status": "Hybrid"},
        },
    )

    report = evaluate_fixture_root(tmp_path / "golden")

    assert report["failed"] == 2
    failures = {(item["field"], item["reason"]) for item in report["failures"]}
    assert ("remote_status", "value_mismatch") in failures
    assert ("work_arrangement.status", "value_mismatch") in failures
    markdown = render_markdown(report)
    assert "fixture-2 · remote_status" in markdown
    assert "Expected: `Hybrid`" in markdown
    assert "Actual: `Remote`" in markdown


def test_baseline_comparison_identifies_regression_and_improvement():
    baseline = {
        "accuracy": 50.0,
        "fixtures": [
            {
                "fixture_id": "one",
                "field_results": [
                    {"field": "remote_status", "passed": True},
                    {"field": "location", "passed": False},
                ],
                "work_arrangement_results": [],
            }
        ],
    }
    current = {
        "accuracy": 50.0,
        "fixtures": [
            {
                "fixture_id": "one",
                "field_results": [
                    {"field": "remote_status", "passed": False},
                    {"field": "location", "passed": True},
                ],
                "work_arrangement_results": [],
            }
        ],
    }

    comparison = compare_to_baseline(current, baseline)

    assert comparison["regressions"] == [
        {"fixture_id": "one", "field": "remote_status"}
    ]
    assert comparison["improvements"] == [
        {"fixture_id": "one", "field": "location"}
    ]
