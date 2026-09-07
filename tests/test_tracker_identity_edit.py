from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

import jaw
from jaw.database import JobDatabase
from jaw.webapp import DashboardServer


def test_job_identity_edit_updates_canonical_values_and_search(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = database.create_job("Original captured description", user_id=0)

    assert database.update_identity(job_id, "Cisco Systems", "Senior SRE", user_id=0)
    job = database.get_job(job_id, user_id=0)
    assert job is not None
    assert job["company"] == "Cisco Systems"
    assert job["title"] == "Senior SRE"
    assert job["raw_description"] == "Original captured description"
    assert [item["id"] for item in database.list_jobs(search="Cisco", user_id=0)] == [job_id]


def test_job_identity_edit_respects_user_scope(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jobs.db")
    job_id = database.create_job("Private job", user_id=3)

    assert not database.update_identity(job_id, "Wrong", "Wrong", user_id=4)
    assert database.update_identity(job_id, "Correct Co", "Platform Engineer", user_id=3)


def test_tracker_identity_endpoint_persists_edit(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    server = DashboardServer(database, port=0, user_data_path=tmp_path / "jaw.db")
    active_user_id = int(server.user_data.read()["active_user_id"])
    job_id = database.create_job("Captured posting", user_id=active_user_id)
    server.start()
    try:
        body = json.dumps({"company": "Canonical Company", "title": "Staff Platform Engineer"}).encode("utf-8")
        request = Request(
            f"{server.url}/api/jobs/{job_id}/identity",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["job"]["company"] == "Canonical Company"
        assert payload["job"]["title"] == "Staff Platform Engineer"
    finally:
        server.stop()


def test_tracker_source_exposes_inline_identity_editor() -> None:
    source = (Path(jaw.__file__).resolve().parent / "dashboard.js").read_text(encoding="utf-8")
    assert "function editTrackerIdentity()" in source
    assert "function saveTrackerIdentity()" in source
    assert "trackerTitleEdit" in source
    assert "trackerCompanyEdit" in source
    assert "/identity`" in source
