from dataclasses import replace
from pathlib import Path

import pytest

from jaw.analyzer import JobAnalyzer
from jaw.config import load_config
from jaw.database import JobDatabase
from jaw.persistence import CaptureRepository, JobRepository, QuestionRepository


def test_database_exposes_focused_repository_boundaries(tmp_path: Path):
    database = JobDatabase(tmp_path / "repositories.db")

    assert isinstance(database.job_repository, JobRepository)
    assert isinstance(database.capture_repository, CaptureRepository)
    assert isinstance(database.question_repository, QuestionRepository)

    job_id = database.job_repository.create_job("Repository-owned job", user_id=3)
    question_id = database.question_repository.add_question(job_id, "Why JAW?")
    session = database.capture_repository.add_capture(3, "Captured posting")

    assert database.get_job(job_id, user_id=3)["questions"][0]["id"] == question_id
    assert session["events"][0]["content"] == "Captured posting"


def test_job_lifecycle(tmp_path: Path):
    config = replace(load_config(), analysis_mode="local")
    database = JobDatabase(tmp_path / "jaw.db")
    description = "Remote SRE using Kubernetes and Terraform. Pay $180,000-$220,000."
    job_id = database.create_job(description)
    result, source = JobAnalyzer(config).analyze(description)
    assert source == "local"
    result["company"] = "Example"
    result["title"] = "Site Reliability Engineer"
    database.update_analysis(job_id, result, "local")
    question_id = database.add_question(job_id, "Why this company?", "Because...")
    database.submit_answer(question_id, "My final answer")
    database.set_status(job_id, "Applied")

    job = database.get_job(job_id)
    assert job is not None
    assert job["status"] == "Applied"
    assert job["applied_at"] is not None
    assert job["remote_status"] == "Remote"
    assert job["questions"][0]["submitted_answer"] == "My final answer"
    listed_job = database.list_jobs(search="Example")[0]
    assert listed_job["id"] == job_id
    assert listed_job["applied_at"] == job["applied_at"]

    database.set_status(job_id, "Interviewing")
    assert database.get_job(job_id)["applied_at"] == job["applied_at"]
    assert database.delete_job(job_id)
    assert database.get_job(job_id) is None
    assert not database.delete_job(job_id)


def test_jobs_can_be_scoped_to_a_user(tmp_path: Path):
    database = JobDatabase(tmp_path / "jobs.db")
    first = database.create_job("First user's job", user_id=1)
    second = database.create_job("Second user's job", user_id=2)
    assert [job["id"] for job in database.list_jobs(user_id=1)] == [first]
    assert [job["id"] for job in database.list_jobs(user_id=2)] == [second]
    assert database.get_job(first, user_id=2) is None
    assert not database.delete_job(first, user_id=2)
    assert database.delete_job(first, user_id=1)


def test_capture_sessions_preserve_history_and_reset(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    first = database.get_or_create_capture_session(7)
    assert first["events"] == []
    first = database.add_capture(7, "Example Company")
    first = database.add_capture(7, "Site Reliability Engineer")
    assert [event["content"] for event in first["events"]] == [
        "Example Company", "Site Reliability Engineer",
    ]
    assert all(event["content_type"] == "unclassified" for event in first["events"])
    assert all(event["classification_status"] == "pending" for event in first["events"])

    application = database.set_capture_phase(7, "application", job_id=None)
    assert application["phase"] == "application"
    database.classify_capture_event(
        int(application["id"]), int(application["events"][0]["id"]),
        "company", {"confidence": 0.9},
    )
    classified = database.active_capture_session(7)
    assert classified is not None
    assert classified["events"][0]["content_type"] == "company"
    assert classified["events"][0]["classification_status"] == "classified"

    second_id = database.start_capture_session(7)
    assert second_id != first["id"]
    second = database.active_capture_session(7)
    assert second is not None
    assert second["events"] == []
    with database.connect() as connection:
        archived = connection.execute(
            "SELECT status FROM capture_sessions WHERE id=?", (first["id"],)
        ).fetchone()
    assert archived["status"] == "cleared"


def test_workflow_bindings():
    config = load_config()
    # Physical bindings are user-configurable; these workflow actions must
    # remain available even when the active user has reassigned their keys.
    assert {"smart_capture", "open_dashboard"}.issubset(
        config.action_labels
    )
    assert "capture_qa" not in config.action_labels


def test_analysis_mode_is_explicit(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = replace(
        load_config(),
        analysis_provider="openai",
        openai_model="gpt-5.6-terra",
    )
    local = JobAnalyzer(replace(config, analysis_mode="local"))
    result, source = local.analyze("Remote Kubernetes role")
    assert source == "local"
    assert result["remote_status"] == "Remote"

    generative = JobAnalyzer(replace(config, analysis_mode="generative"))
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        generative.analyze("Remote Kubernetes role")
