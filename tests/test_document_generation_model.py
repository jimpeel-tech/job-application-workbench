from __future__ import annotations

from pathlib import Path

import pytest

from jaw.application.document_workbench_application import DocumentWorkbenchApplication
from jaw.database import JobDatabase
from jaw.documents.text_generation import DEFAULT_OLLAMA_MODEL
from jaw.userdata import UserDataStore


def _application(tmp_path: Path) -> tuple[UserDataStore, DocumentWorkbenchApplication, int]:
    database_path = tmp_path / "data" / "jaw.db"
    store = UserDataStore(database_path)
    database = JobDatabase(database_path)
    user_id = int(store.read()["active_user_id"])
    return store, DocumentWorkbenchApplication(database, store), user_id


def test_document_generation_settings_inherit_active_user_settings(tmp_path: Path) -> None:
    store, application, user_id = _application(tmp_path)
    store.save_analysis_settings("generative", "openai", "gpt-user-choice")

    settings = application.generation_settings(user_id)

    assert settings == {"provider": "openai", "model": "gpt-user-choice"}


def test_document_generation_override_does_not_mutate_job_analysis_settings(
    tmp_path: Path,
) -> None:
    store, application, user_id = _application(tmp_path)
    store.save_analysis_settings("generative", "openai", "gpt-user-choice")

    settings = application.generation_settings(
        user_id,
        {
            "generation_provider": "ollama",
            "generation_model": "qwen3:14b",
        },
    )

    assert settings == {"provider": "ollama", "model": "qwen3:14b"}
    assert store.read()["analysis_settings"] == {
        "mode": "generative",
        "provider": "openai",
        "model": "gpt-user-choice",
    }


def test_changing_document_provider_without_model_uses_provider_default(
    tmp_path: Path,
) -> None:
    store, application, user_id = _application(tmp_path)
    store.save_analysis_settings("generative", "openai", "gpt-user-choice")

    settings = application.generation_settings(
        user_id,
        {"generation_provider": "ollama"},
    )

    assert settings == {"provider": "ollama", "model": DEFAULT_OLLAMA_MODEL}


def test_document_generation_rejects_unknown_provider(tmp_path: Path) -> None:
    _, application, user_id = _application(tmp_path)

    with pytest.raises(ValueError, match="OpenAI or Ollama"):
        application.generation_settings(
            user_id,
            {
                "generation_provider": "unknown",
                "generation_model": "model",
            },
        )


def test_documents_status_bar_exposes_generation_model_override_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    javascript = (root / "src/jaw/document_workbench_preview.js").read_text(
        encoding="utf-8"
    )
    application = (
        root / "src/jaw/application/document_workbench_application.py"
    ).read_text(encoding="utf-8")

    assert "wbStatusGenerationModel" in javascript
    assert "Document Generation Model" in javascript
    assert "Use user setting" in javascript
    assert "generation_provider" in javascript
    assert "generation_model" in javascript
    assert "Job Analysis settings are unchanged" in javascript
    assert "analysis_settings = self.generation_settings(user_id, payload)" in application
