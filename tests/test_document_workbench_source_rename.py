from __future__ import annotations

from pathlib import Path

from jaw.application.document_workbench_resource_service import rename_reference_symbol
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def _service(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    return database, service


def _document(state: dict, document_id: str) -> dict:
    return next(item for item in state["documents"] if item["id"] == document_id)


def test_checkpoint_does_not_guess_private_section_rename(tmp_path: Path) -> None:
    _, service = _service(tmp_path)
    document = service.create_document(1, {"name": "Resume"})
    original = document["sections"][0]
    service.save(1, {"resource_id": original["id"], "content": "Keep this section."})

    source = document["template"]["content"].replace("{{ section }}", "{{ experience }}")
    result = service.checkpoint(
        1,
        {
            "resource_id": document["template_id"],
            "document_id": document["id"],
            "content": source,
        },
    )

    current = _document(result["state"], document["id"])
    by_symbol = {item["reference_symbol"]: item for item in current["sections"]}
    assert set(by_symbol) == {"section", "experience"}
    assert by_symbol["section"]["id"] == original["id"]
    assert by_symbol["section"]["name"] == ""
    assert by_symbol["section"]["content"] == "Keep this section."
    assert by_symbol["experience"]["id"] != original["id"]
    assert by_symbol["experience"]["name"] == ""
    assert result["changes"]["created"] == [by_symbol["experience"]["id"]]
    assert result["changes"]["orphaned"] == []
    assert result["changes"]["deleted"] == []


def test_checkpoint_does_not_guess_private_function_rename(tmp_path: Path) -> None:
    _, service = _service(tmp_path)
    document = service.create_document(1, {"name": "Resume"})
    section = document["sections"][0]
    service.save(1, {"resource_id": section["id"], "content": "{{ helper }}"})
    original = _document(service.state(1), document["id"])["sections"][0]["functions"][0]
    service.save(1, {"resource_id": original["id"], "content": "Reusable helper body"})

    result = service.checkpoint(
        1,
        {"resource_id": section["id"], "content": "{{ formatter }}"},
    )

    current = _document(result["state"], document["id"])
    by_symbol = {
        item["reference_symbol"]: item
        for item in current["sections"][0]["functions"]
    }
    assert set(by_symbol) == {"helper", "formatter"}
    assert by_symbol["helper"]["id"] == original["id"]
    assert by_symbol["helper"]["name"] == ""
    assert by_symbol["helper"]["content"] == "Reusable helper body"
    assert by_symbol["formatter"]["id"] != original["id"]
    assert by_symbol["formatter"]["name"] == ""
    assert result["changes"]["created"] == [by_symbol["formatter"]["id"]]
    assert result["changes"]["orphaned"] == []
    assert result["changes"]["deleted"] == []


def test_multi_symbol_replacement_is_additive_and_never_deletes_original(tmp_path: Path) -> None:
    _, service = _service(tmp_path)
    document = service.create_document(1, {"name": "Resume"})
    original = document["sections"][0]

    source = document["template"]["content"].replace(
        "{{ section }}",
        "{{ summary }}\n{{ experience }}",
    )
    result = service.checkpoint(
        1,
        {
            "resource_id": document["template_id"],
            "document_id": document["id"],
            "content": source,
        },
    )

    current = _document(result["state"], document["id"])
    by_symbol = {item["reference_symbol"]: item for item in current["sections"]}
    assert set(by_symbol) == {"section", "summary", "experience"}
    assert by_symbol["section"]["id"] == original["id"]
    assert len(result["changes"]["created"]) == 2
    assert result["changes"]["orphaned"] == []
    assert result["changes"]["deleted"] == []


def test_explicit_rename_updates_private_symbol_without_creating_a_name(
    tmp_path: Path,
) -> None:
    database, service = _service(tmp_path)
    document = service.create_document(
        1,
        {
            "name": "Resume",
            "template_source": "\\begin{document}\n{{ section }}\n\\end{document}\n",
        },
    )
    section = document["sections"][0]

    result = rename_reference_symbol(
        database.document_workbench_repository,
        1,
        {
            "parent_id": document["id"],
            "child_id": section["id"],
            "symbol": "experience",
        },
    )

    repository = database.document_workbench_repository
    renamed = repository.require_resource(1, section["id"])
    template = repository.require_resource(1, document["template_id"])
    assert renamed["id"] == section["id"]
    assert renamed["symbol"] == "experience"
    assert renamed["name"] == ""
    assert "{{ experience }}" in template["content"]
    assert result["changed"] is True
