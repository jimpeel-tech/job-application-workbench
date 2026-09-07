from __future__ import annotations

from pathlib import Path

import pytest

from jaw.application.document_generation_context import DocumentGenerationContext
from jaw.application.document_workbench_application import DocumentWorkbenchApplication
from jaw.database import JobDatabase


class _UserData:
    def read(self, *, user_id=None):
        return {
            "user": {
                "first_name": "Real",
                "last_name": "User",
                "email": "real.user@example.test",
            },
            "work_history": [
                {
                    "id": "work_real",
                    "enabled": True,
                    "company": "Real Employer",
                    "title": "Real Role",
                }
            ],
            "capability_model": {
                "entities": [
                    {
                        "id": "cap_real",
                        "type": "technology",
                        "canonical_name": "Real Skill",
                        "display_name": "Real Skill",
                        "aliases": [],
                        "rating": 4,
                        "match_enabled": True,
                    }
                ],
                "relationships": [],
                "view_preferences": {},
            },
            "analysis_settings": {},
        }


def _analyzed_job(
    database: JobDatabase,
    *,
    user_id: int,
    company: str,
    title: str,
) -> int:
    job_id = database.create_job(f"{company} {title}", user_id=user_id)
    database.update_analysis(
        job_id,
        {
            "company": company,
            "title": title,
            "summary": f"Summary for {company}",
        },
        "test-model",
    )
    return job_id


def test_automatic_context_uses_newest_tracked_job(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    first = _analyzed_job(
        database,
        user_id=1,
        company="Older Company",
        title="Older Title",
    )
    latest = _analyzed_job(
        database,
        user_id=1,
        company="Latest Company",
        title="Latest Title",
    )
    assert latest > first

    contexts = DocumentGenerationContext(database, _UserData())
    info = contexts.info(1)
    context = contexts.context_mapping(1, require_job=True)

    assert info["mode"] == "auto"
    assert info["effective_job_id"] == latest
    assert info["label"] == "Automatic · Latest Company · Latest Title"
    assert context["job_ref"]["company"] == "Latest Company"
    assert context["job_ref"]["title"] == "Latest Title"
    assert context["job_ref"]["score"] is None
    assert context["user"]["full_name"] == "Real User"
    assert context["cap"]["all"][0]["name"] == "Real Skill"
    assert context["work_exp"][0]["company"] == "Real Employer"
    assert "job" not in context
    assert "capabilities" not in context
    assert "work_history" not in context


def test_selected_job_context_persists_per_user(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    first = _analyzed_job(
        database,
        user_id=1,
        company="Chosen Company",
        title="Chosen Title",
    )
    _analyzed_job(
        database,
        user_id=1,
        company="Newer Company",
        title="Newer Title",
    )

    contexts = DocumentGenerationContext(database, _UserData())
    contexts.set_selection(1, {"mode": "selected", "job_id": first})

    reloaded = DocumentGenerationContext(database, _UserData())
    info = reloaded.info(1)
    context = reloaded.context_mapping(1, require_job=True)

    assert info["mode"] == "selected"
    assert info["job_id"] == first
    assert info["effective_job_id"] == first
    assert info["label"] == "Selected · Chosen Company · Chosen Title"
    assert context["job_ref"]["title"] == "Chosen Title"


def test_example_context_is_unmistakably_example_data(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    contexts = DocumentGenerationContext(database, _UserData())

    contexts.set_selection(1, {"mode": "example"})
    info = contexts.info(1)
    context = contexts.context_mapping(1, require_job=True)

    assert info["mode"] == "example"
    assert info["label"] == "EXAMPLE DATA · Example Company · Example Title"
    assert context["user"]["full_name"] == "Example User"
    assert context["job_ref"]["company"] == "Example Company"
    assert context["job_ref"]["title"] == "Example Title"
    assert context["cap"]["all"][0]["name"] == "Example Skill 1"
    assert context["cap"]["sets"]["platform_sre"][0]["name"] == "Example Skill 1"


def test_automatic_context_never_falls_back_to_example_data(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    contexts = DocumentGenerationContext(database, _UserData())

    info = contexts.info(1)
    context = contexts.context_mapping(1, require_job=False)

    assert info["mode"] == "auto"
    assert info["can_generate"] is False
    assert "No tracked jobs available" in info["error"]
    assert context["source"] == "real:no-job"
    assert context["user"]["full_name"] == "Real User"
    assert context["job_ref"] == {}
    assert context["cap"]["all"][0]["name"] == "Real Skill"

    with pytest.raises(ValueError, match="No tracked jobs available"):
        contexts.context_mapping(1, require_job=True)


def test_selected_context_rejects_job_owned_by_another_user(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    other_job = _analyzed_job(
        database,
        user_id=2,
        company="Other Company",
        title="Other Title",
    )
    contexts = DocumentGenerationContext(database, _UserData())

    with pytest.raises(ValueError, match="not found"):
        contexts.set_selection(1, {"mode": "selected", "job_id": other_job})


def test_workbench_state_uses_real_automatic_context_and_exposes_selection(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    latest = _analyzed_job(
        database,
        user_id=1,
        company="Workbench Company",
        title="Workbench Title",
    )
    application = DocumentWorkbenchApplication(database, _UserData())

    state = application.state(1)

    assert state["generation_context"]["job_ref"]["title"] == "Workbench Title"
    assert state["generation_context_info"]["mode"] == "auto"
    assert state["generation_context_info"]["effective_job_id"] == latest


def test_context_only_save_does_not_clear_document_routing(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    application = DocumentWorkbenchApplication(database, _UserData())
    document = application.create_document(1, {"name": "Default Document"})
    application.save_routing(
        1,
        {
            "rules": [],
            "default_document_id": document["id"],
        },
    )

    routing = application.save_routing(
        1,
        {"generation_context": {"mode": "example"}},
    )

    assert routing["default_document_id"] == document["id"]
    assert application.state(1)["generation_context_info"]["mode"] == "example"
