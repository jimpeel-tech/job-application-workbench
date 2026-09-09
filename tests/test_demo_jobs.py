from __future__ import annotations

import json
from pathlib import Path

from jaw import database as database_module
from jaw.database import JobDatabase
from jaw.demo_jobs import seed_packaged_demo_jobs
from jaw.userdata import UserDataStore


def _write_fixture(path: Path) -> Path:
    payload = {
        "format": "jaw-demo-jobs",
        "version": 1,
        "jobs": [
            {
                "company": "12th Man Software",
                "title": "Senior Software Engineer",
                "location": "Austin, TX",
                "remote_status": "Hybrid",
                "source_url": "",
                "raw_description": "Build distributed services in Python and TypeScript.",
                "pay_min": 155000,
                "pay_max": 190000,
                "currency": "USD",
                "pay_period": "year",
                "pay_disclosed": True,
                "match_score": 87,
                "summary": "Strong match for a senior backend-focused engineer.",
                "strong_matches": ["Python", "API Design", "Distributed Systems"],
                "concerns": ["Limited Go experience"],
                "missing_qualifications": ["Go"],
                "status": "Applied",
                "events": [
                    {
                        "event_type": "Captured",
                        "details": "",
                        "source": "manual",
                        "source_ref": None,
                        "metadata": {},
                    },
                    {
                        "event_type": "Analyzed",
                        "details": "Model: demo-model",
                        "source": "manual",
                        "source_ref": None,
                        "metadata": {},
                    },
                    {
                        "event_type": "Applied",
                        "details": "",
                        "source": "manual",
                        "source_ref": None,
                        "metadata": {},
                    },
                ],
                "analysis_runs": [
                    {
                        "model": "demo-model",
                        "prompt_version": "brief-v1",
                        "raw_result": {
                            "company": "12th Man Software",
                            "title": "Senior Software Engineer",
                            "match_score": 87,
                        },
                    }
                ],
                "questions": [
                    {
                        "question": "What is a past achievement that you would like to highlight?",
                        "suggested_answer": "Led a distributed-services redesign.",
                        "submitted_answer": "Reduced infrastructure cost by 40%.",
                    }
                ],
            }
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _demo_database(tmp_path: Path) -> tuple[JobDatabase, int]:
    target_database = tmp_path / "data" / "jaw.db"
    store = UserDataStore(target_database)
    user_id = int(store.read()["active_user_id"])
    database = JobDatabase(target_database, seed_demo=False)
    return database, user_id


def test_demo_seed_restores_tracker_state_once_and_deleted_jobs_stay_deleted(tmp_path: Path):
    fixture = _write_fixture(tmp_path / "demo-jobs.json")
    database, user_id = _demo_database(tmp_path)

    with database.connect() as connection:
        assert seed_packaged_demo_jobs(connection, fixture) == 1

    jobs = database.list_jobs(user_id=user_id)
    assert len(jobs) == 1
    job = database.get_job(int(jobs[0]["id"]), user_id=user_id)
    assert job is not None
    assert job["company"] == "12th Man Software"
    assert job["title"] == "Senior Software Engineer"
    assert job["status"] == "Applied"
    assert job["match_score"] == 87
    assert job["strong_matches"] == ["Python", "API Design", "Distributed Systems"]
    assert job["concerns"] == ["Limited Go experience"]
    assert job["missing_qualifications"] == ["Go"]
    assert job["applied_at"] is not None
    assert [event["event_type"] for event in reversed(job["events"])] == [
        "Captured",
        "Analyzed",
        "Applied",
    ]
    assert len(job["questions"]) == 1
    question = job["questions"][0]
    assert question["question"] == "What is a past achievement that you would like to highlight?"
    assert question["suggested_answer"] == "Led a distributed-services redesign."
    assert question["submitted_answer"] == "Reduced infrastructure cost by 40%."
    assert question["submitted_at"] is not None

    with database.connect() as connection:
        run = connection.execute(
            "SELECT model,prompt_version,raw_result FROM analysis_runs WHERE job_id=?",
            (int(job["id"]),),
        ).fetchone()
    assert run is not None
    assert run["model"] == "demo-model"
    assert run["prompt_version"] == "brief-v1"
    assert json.loads(run["raw_result"])["match_score"] == 87

    assert database.delete_job(int(job["id"]), user_id=user_id) is True
    with database.connect() as connection:
        assert seed_packaged_demo_jobs(connection, fixture) == 0
    assert database.list_jobs(user_id=user_id) == []


def test_demo_seed_skips_existing_source_job_and_records_seed_version(tmp_path: Path):
    fixture = _write_fixture(tmp_path / "demo-jobs.json")
    database, user_id = _demo_database(tmp_path)

    job_id = database.create_job(
        "Build distributed services in Python and TypeScript.",
        user_id=user_id,
    )
    assert database.update_identity(
        job_id,
        "12th Man Software",
        "Senior Software Engineer",
        user_id=user_id,
    )

    with database.connect() as connection:
        assert seed_packaged_demo_jobs(connection, fixture) == 0

    assert len(database.list_jobs(user_id=user_id)) == 1
    assert database.delete_job(job_id, user_id=user_id) is True

    with database.connect() as connection:
        assert seed_packaged_demo_jobs(connection, fixture) == 0
    assert database.list_jobs(user_id=user_id) == []


def test_demo_seed_only_targets_active_ol_sarge_account(tmp_path: Path):
    fixture = _write_fixture(tmp_path / "demo-jobs.json")
    target_database = tmp_path / "data" / "jaw.db"
    store = UserDataStore(target_database)
    real_user_id = store.create_user("Real User")
    store.switch_user(real_user_id)
    database = JobDatabase(target_database, seed_demo=False)

    with database.connect() as connection:
        assert seed_packaged_demo_jobs(connection, fixture) == 0

    assert database.list_jobs(user_id=real_user_id) == []


def test_normal_database_initialization_invokes_demo_seeder(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JAW_HOME", str(tmp_path))
    target_database = database_module.database_path()
    UserDataStore(target_database)
    calls: list[bool] = []

    def fake_seed(connection) -> int:
        calls.append(connection is not None)
        return 0

    monkeypatch.setattr(database_module, "seed_packaged_demo_jobs", fake_seed)
    JobDatabase(target_database)

    assert calls == [True]
