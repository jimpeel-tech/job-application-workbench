import json

import pytest

from jaw.application import CaptureService, CaptureValidationError
from jaw.capture import JOB_EXTRACTOR_VERSION
from jaw.database import JobDatabase


def test_capture_service_validates_and_persists_job_description(tmp_path):
    database = JobDatabase(tmp_path / "jaw.db")
    service = CaptureService(database)

    accepted = service.accept_text(
        7,
        "Platform Engineer\nResponsibilities\n"
        "Build reliable Kubernetes services.\nQualifications\nKubernetes experience.",
    )

    assert accepted.classification.content_type == "job_description"
    event = accepted.session["events"][-1]
    assert event["classification_status"] == "classified"
    metadata = json.loads(event["metadata"])
    assert metadata["extraction"]["extractor"] == JOB_EXTRACTOR_VERSION


def test_capture_service_pairs_application_question_and_answer(tmp_path):
    database = JobDatabase(tmp_path / "jaw.db")
    job_id = database.create_job("Example posting", user_id=7)
    database.set_capture_phase(7, "application", job_id)
    service = CaptureService(
        database,
        answer_matcher=lambda question: f"Suggested for {question}",
    )

    service.accept_text(7, "Why do you want this role?")
    service.accept_text(7, "It matches my platform engineering experience.")

    job = database.get_job(job_id)
    assert job is not None
    assert job["questions"] == [
        {
            **job["questions"][0],
            "question": "Why do you want this role?",
            "suggested_answer": "Suggested for Why do you want this role?",
            "submitted_answer": "It matches my platform engineering experience.",
        }
    ]


def test_capture_service_refreshes_stale_extraction(tmp_path):
    database = JobDatabase(tmp_path / "jaw.db")
    database.add_capture(
        7,
        "Platform Engineer\nResponsibilities\nBuild reliable services.",
        content_type="job_description",
        classification_status="classified",
        metadata={"extraction": {"extractor": "rules-v1"}},
    )
    service = CaptureService(database)

    refreshed = service.refresh_session(7)

    metadata = json.loads(refreshed["events"][0]["metadata"])
    assert metadata["extraction"]["extractor"] == JOB_EXTRACTOR_VERSION


@pytest.mark.parametrize("content", ["", "   ", "bad\x00text"])
def test_capture_service_rejects_invalid_selection(content, tmp_path):
    service = CaptureService(JobDatabase(tmp_path / "jaw.db"))

    with pytest.raises(CaptureValidationError, match="Capture failed"):
        service.accept_text(7, content)


def test_capture_service_records_application_form_prompt_without_question_mark(tmp_path):
    database = JobDatabase(tmp_path / "jaw.db")
    job_id = database.create_job("Example posting", user_id=7)
    database.set_capture_phase(7, "application", job_id)
    service = CaptureService(database)

    accepted = service.accept_text(7, "Years of experience with Kubernetes")

    assert accepted.classification.content_type == "application_question"
    job = database.get_job(job_id)
    assert job is not None
    assert job["questions"][0]["question"] == "Years of experience with Kubernetes"
