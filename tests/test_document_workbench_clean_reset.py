from __future__ import annotations

from pathlib import Path

from jaw.application.document_workbench_application import DocumentWorkbenchApplication
from jaw.application.document_workbench_resource_service import delete_unreferenced_resource
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase
from jaw.document_db_audit import audit, document_store_is_clean


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def test_deleting_last_document_removes_private_template_and_owned_tree(
    tmp_path: Path,
) -> None:
    path = tmp_path / "jaw.db"
    database = JobDatabase(path)
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())

    first = service.create_document(1, {"name": "First"})
    second = service.create_document(1, {"name": "Second"})
    first_template_id = first["template_id"]
    second_template_id = second["template_id"]
    assert first_template_id != second_template_id

    # Exercise recovery-buffer cleanup as part of Document deletion too.
    service.checkpoint(
        1,
        {
            "resource_id": second["sections"][0]["id"],
            "content": "Unsaved text",
        },
    )

    first_deleted = delete_unreferenced_resource(
        repository, 1, {"resource_id": first["id"]}
    )
    assert first["id"] in first_deleted["deleted"]
    assert first_template_id in first_deleted["deleted"]
    assert repository.get_resource(1, first_template_id) is None
    assert repository.get_document(1, second["id"]) is not None
    assert repository.get_resource(1, second_template_id) is not None

    second_deleted = delete_unreferenced_resource(
        repository, 1, {"resource_id": second["id"]}
    )
    assert second["id"] in second_deleted["deleted"]
    assert second_template_id in second_deleted["deleted"]
    assert repository.list_documents(1) == []
    assert repository.list_resources(1) == []
    assert repository.list_edges(1) == []
    assert repository.list_buffers(1) == []

    empty = audit(path)
    assert document_store_is_clean(empty) is True


def test_application_state_does_not_create_hidden_template_resources(tmp_path: Path) -> None:
    path = tmp_path / "jaw.db"
    database = JobDatabase(path)
    repository = database.document_workbench_repository
    application = DocumentWorkbenchApplication(database, _UserData())

    assert application.state(1)["documents"] == []
    assert repository.list_resources(1) == []

    document = application.create_document(1, {"name": "Created"})
    template = repository.require_resource(1, document["template_id"])
    assert template["name"] == "Created"
    assert template["visibility"] == "private"
    assert template["owner_id"] == document["id"]
    assert template["settings"].get("system_template") is None
    assert template["settings"].get("starter") is None
    assert template["settings"].get("immutable") is None
