from __future__ import annotations

import json
from pathlib import Path

from jaw.database import JobDatabase
from jaw.importers.spreadsheet_applications import (
    import_spreadsheet_applications,
    resolve_user_id,
)
from jaw.persistence import UserRepository


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _approved_fixture(root: Path, fixture_id: str = "005-example-staff-sre") -> None:
    root.mkdir(parents=True, exist_ok=True)
    _write_json(
        root / f"{fixture_id}.expected.json",
        {
            "fixture_id": fixture_id,
            "company": "Example Corp",
            "title": "Staff SRE",
            "location": "Austin, TX",
            "remote_status": "Remote or hybrid",
            "source_url": "https://example.com/jobs/5",
            "raw_description": "Example Corp\n\nStaff SRE\n\nBuild reliable systems.",
            "pay_min": "150000",
            "pay_max": "200000",
            "currency": "USD",
            "pay_period": "year",
            "application_questions": ["Why are you interested?"],
            "annotation": {
                "method": "independent_manual_review",
                "reviewer": "Codex",
            },
        },
    )
    _write_json(
        root / f"{fixture_id}.capture.json",
        {
            "manifest": {
                "fixture_id": fixture_id,
                "status": "approved",
                "source_site": "Spreadsheet: Applied",
                "source": {"sheet": "Applied", "row": 5, "date": "2025-11-03"},
            },
            "captures": [],
        },
    )


def _user(database_path: Path, name: str = "Jim") -> int:
    repository = UserRepository(database_path)
    with repository.transaction() as session:
        session.initialize_schema()
        return session.create_user(name, {"user": {"first_name": name}})


def test_importer_dry_run_then_imports_historical_application_idempotently(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jaw.db"
    user_id = _user(database_path)
    source_dir = tmp_path / "spreadsheet_approved"
    _approved_fixture(source_dir)
    database = JobDatabase(database_path)

    dry_run = import_spreadsheet_applications(
        database,
        user_id=user_id,
        source_dir=source_dir,
    )
    assert dry_run.approved == 1
    assert dry_run.imported == 0
    assert dry_run.already_imported == 0
    assert dry_run.dry_run is True
    assert database.list_jobs(user_id=user_id) == []

    applied = import_spreadsheet_applications(
        database,
        user_id=user_id,
        source_dir=source_dir,
        apply=True,
    )
    assert applied.imported == 1
    assert applied.already_imported == 0

    jobs = database.list_jobs(user_id=user_id)
    assert len(jobs) == 1
    job = database.get_job(jobs[0]["id"], user_id=user_id)
    assert job is not None
    assert job["company"] == "Example Corp"
    assert job["title"] == "Staff SRE"
    assert job["location"] == "Austin, TX"
    assert job["remote_status"] == "Remote or hybrid"
    assert job["source_url"] == "https://example.com/jobs/5"
    assert job["pay_min"] == 150000
    assert job["pay_max"] == 200000
    assert job["status"] == "Applied"
    assert job["applied_at"] == "2025-11-03"
    assert job["created_at"] == "2025-11-03"
    assert job["questions"][0]["question"] == "Why are you interested?"
    assert [event["event_type"] for event in job["events"]] == ["Applied", "Imported"]
    assert job["events"][1]["details"] == "Spreadsheet fixture: 005-example-staff-sre"

    repeated = import_spreadsheet_applications(
        database,
        user_id=user_id,
        source_dir=source_dir,
        apply=True,
    )
    assert repeated.imported == 0
    assert repeated.already_imported == 1
    assert len(database.list_jobs(user_id=user_id)) == 1


def test_importer_ignores_unapproved_capture_manifest(tmp_path: Path) -> None:
    database_path = tmp_path / "jaw.db"
    user_id = _user(database_path)
    source_dir = tmp_path / "spreadsheet_approved"
    _approved_fixture(source_dir)

    capture_path = source_dir / "005-example-staff-sre.capture.json"
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    capture["manifest"]["status"] = "awaiting_codex"
    _write_json(capture_path, capture)

    result = import_spreadsheet_applications(
        JobDatabase(database_path),
        user_id=user_id,
        source_dir=source_dir,
        apply=True,
    )
    assert result.approved == 0
    assert result.imported == 0
    assert result.ignored_unapproved == 1


def test_resolve_user_id_accepts_unique_case_insensitive_name(tmp_path: Path) -> None:
    database_path = tmp_path / "jaw.db"
    user_id = _user(database_path, "Jim")

    assert resolve_user_id(database_path, "jim") == user_id
