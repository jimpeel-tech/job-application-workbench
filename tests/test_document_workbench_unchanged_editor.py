from __future__ import annotations

from pathlib import Path

from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def test_unchanged_starter_checkpoint_does_not_clone_or_leave_recovery_buffer(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(1, {"name": "Resume"})
    starter_id = document["template_id"]

    result = service.checkpoint(
        1,
        {
            "resource_id": starter_id,
            "document_id": document["id"],
            "content": document["template"]["content"],
            "cursor_start": 5,
            "cursor_end": 5,
        },
    )

    assert "template_replaced" not in result
    assert result["buffer"] == {}
    assert repository.get_buffer(1, starter_id) is None
    current = repository.get_document(1, document["id"])
    assert current is not None
    assert current["template_id"] == starter_id


def test_reverting_private_resource_to_saved_content_clears_recovery_buffer(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(
        1,
        {"name": "Resume", "template_source": "{{ section }}"},
    )
    section = document["sections"][0]

    service.checkpoint(
        1,
        {"resource_id": section["id"], "content": "Unsaved draft"},
    )
    assert repository.get_buffer(1, section["id"]) is not None

    result = service.checkpoint(
        1,
        {"resource_id": section["id"], "content": section["content"]},
    )

    assert result["buffer"] == {}
    assert repository.get_buffer(1, section["id"]) is None
    restored = next(
        item for item in result["state"]["resources"] if item["id"] == section["id"]
    )
    assert restored["dirty"] is False
