from __future__ import annotations

from pathlib import Path

from jaw.application.document_workbench_application import DocumentWorkbenchApplication
from jaw.database import JobDatabase


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def _app(tmp_path: Path) -> tuple[JobDatabase, DocumentWorkbenchApplication]:
    database = JobDatabase(tmp_path / "jaw.db")
    return database, DocumentWorkbenchApplication(database, _UserData())


def test_private_template_becomes_global_without_changing_jid(tmp_path: Path) -> None:
    database, app = _app(tmp_path)
    document = app.create_document(1, {"name": "Resume"})
    template = document["template"]

    result = app.update_resource(
        1,
        {"resource_id": template["id"], "visibility": "global"},
    )

    saved = database.document_workbench_repository.require_resource(1, template["id"])
    assert saved["id"] == template["id"]
    assert saved["visibility"] == "global"
    assert saved["owner_id"] is None
    assert result["resource"]["id"] == template["id"]


def test_single_use_global_template_becomes_private_in_place(tmp_path: Path) -> None:
    database, app = _app(tmp_path)
    document = app.create_document(1, {"name": "Resume"})
    template = document["template"]
    app.update_resource(1, {"resource_id": template["id"], "visibility": "global"})

    result = app.update_resource(
        1,
        {
            "resource_id": template["id"],
            "visibility": "private",
            "owner_id": document["id"],
        },
    )

    saved = database.document_workbench_repository.require_resource(1, template["id"])
    assert saved["id"] == template["id"]
    assert saved["visibility"] == "private"
    assert saved["owner_id"] == document["id"]
    assert result["template_detached"] is None


def test_shared_global_template_detaches_active_document_to_private_clone(
    tmp_path: Path,
) -> None:
    database, app = _app(tmp_path)
    repository = database.document_workbench_repository
    first = app.create_document(1, {"name": "First"})
    second = app.create_document(1, {"name": "Second"})
    shared = first["template"]

    app.update_resource(1, {"resource_id": shared["id"], "visibility": "global"})
    app.update_resource(
        1,
        {"resource_id": second["id"], "template_id": shared["id"]},
    )
    assert len(repository.documents_for_template(1, shared["id"])) == 2

    result = app.update_resource(
        1,
        {
            "resource_id": shared["id"],
            "visibility": "private",
            "owner_id": second["id"],
        },
    )

    detached = result["template_detached"]
    assert detached["global_template_id"] == shared["id"]
    assert detached["document_id"] == second["id"]
    assert detached["private_template_id"] != shared["id"]

    global_template = repository.require_resource(1, shared["id"])
    private_template = repository.require_resource(1, detached["private_template_id"])
    first_document = repository.get_document(1, first["id"])
    second_document = repository.get_document(1, second["id"])
    assert first_document is not None
    assert second_document is not None
    assert first_document["template_id"] == shared["id"]
    assert second_document["template_id"] == private_template["id"]
    assert global_template["visibility"] == "global"
    assert global_template["owner_id"] is None
    assert private_template["visibility"] == "private"
    assert private_template["owner_id"] == second["id"]
    assert private_template["content"] == global_template["content"]
    assert private_template["settings"] == global_template["settings"]
