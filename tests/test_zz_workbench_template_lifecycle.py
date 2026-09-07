from __future__ import annotations

from pathlib import Path

from jaw.application.document_workbench_application import DocumentWorkbenchApplication
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def test_new_documents_own_private_templates_from_creation(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    first = service.create_document(1, {"name": "First"})
    second = service.create_document(1, {"name": "Second"})

    assert first["template_id"] != second["template_id"]
    first_template = database.document_workbench_repository.require_resource(
        1, first["template_id"]
    )
    second_template = database.document_workbench_repository.require_resource(
        1, second["template_id"]
    )
    assert first_template["name"] == "First"
    assert second_template["name"] == "Second"
    assert first_template["visibility"] == second_template["visibility"] == "private"
    assert first_template["owner_id"] == first["id"]
    assert second_template["owner_id"] == second["id"]
    assert first_template["settings"].get("system_template") is None
    assert second_template["settings"].get("starter") is None
    assert second_template["settings"].get("immutable") is None

    edited_source = first_template["content"].replace("{{ section }}", "{{ intro }}")
    result = service.checkpoint(
        1,
        {
            "resource_id": first_template["id"],
            "document_id": first["id"],
            "content": edited_source,
        },
    )

    assert "template_replaced" not in result
    refreshed_first = database.document_workbench_repository.get_document(1, first["id"])
    refreshed_second = database.document_workbench_repository.get_document(1, second["id"])
    assert refreshed_first is not None
    assert refreshed_second is not None
    assert refreshed_first["template_id"] == first_template["id"]
    assert refreshed_second["template_id"] == second_template["id"]


def test_rename_symbol_keeps_template_jid_and_rewrites_private_template(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    application = DocumentWorkbenchApplication(database, _UserData())
    document = application.create_document(1, {"name": "Resume"})
    template = document["template"]
    section = document["sections"][0]

    result = application.rename_symbol(
        1,
        {
            "reference_id": section["reference_id"],
            "parent_id": document["id"],
            "child_id": section["id"],
            "symbol": "intro",
        },
    )

    assert "template_replaced" not in result
    repository = database.document_workbench_repository
    current_document = repository.get_document(1, document["id"])
    assert current_document is not None
    assert current_document["template_id"] == template["id"]
    current_template = repository.require_resource(1, template["id"])
    assert current_template["visibility"] == "private"
    assert current_template["owner_id"] == document["id"]
    assert "{{ intro }}" in current_template["content"]
    assert "{{ section }}" not in current_template["content"]
    assert repository.get_buffer(1, template["id"]) is None
