from __future__ import annotations

from pathlib import Path

from jaw.application.document_workbench_application import DocumentWorkbenchApplication
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def _document(state: dict, document_id: str) -> dict:
    return next(item for item in state["documents"] if item["id"] == document_id)


def test_explicit_create_preserves_zero_occurrence_order(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    application = DocumentWorkbenchApplication(database, _UserData())
    document = application.create_document(
        1,
        {"name": "Replace First", "template_source": "{{ section }}"},
    )
    section = document["sections"][0]

    result = application.transition_reference(
        1,
        {
            "action": "create",
            "reference_id": section["reference_id"],
            "parent_id": document["id"],
            "child_id": section["id"],
            "symbol": "experience",
            "reference_start": 3,
            "reference_end": 13,
            "source_content": "{{ experience }}",
            "disposition": "stage",
        },
    )

    edges = database.document_workbench_repository.list_edges(1, document["id"])
    assert len(edges) == 1
    assert edges[0]["id"] == result["created_reference_ids"][0]
    assert edges[0]["symbol"] == "experience"
    assert edges[0]["sort_order"] == 0
    assert result["staged"] is True


def test_checkpoint_hints_preserve_shifted_duplicate_reference_jids(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(
        1,
        {
            "name": "Shifted Duplicate Sections",
            "template_source": "{{ body }}\n{{ body }}",
        },
    )
    original_first, original_second = document["sections"]

    source = "{{ body }}\n{{ body }}\n{{ body }}"
    result = service.checkpoint(
        1,
        {
            "resource_id": document["template_id"],
            "document_id": document["id"],
            "content": source,
            "reference_bindings": [
                {
                    "reference_id": original_first["reference_id"],
                    "start": 14,
                    "end": 18,
                    "symbol": "body",
                },
                {
                    "reference_id": original_second["reference_id"],
                    "start": 25,
                    "end": 29,
                    "symbol": "body",
                },
            ],
        },
    )

    current = _document(result["state"], document["id"])
    inserted, first, second = current["sections"]
    assert inserted["id"] not in {original_first["id"], original_second["id"]}
    assert inserted["reference_id"] not in {
        original_first["reference_id"],
        original_second["reference_id"],
    }
    assert first["id"] == original_first["id"]
    assert first["reference_id"] == original_first["reference_id"]
    assert second["id"] == original_second["id"]
    assert second["reference_id"] == original_second["reference_id"]

    edges = repository.list_edges(1, document["id"])
    assert [edge["id"] for edge in edges] == [
        inserted["reference_id"],
        original_first["reference_id"],
        original_second["reference_id"],
    ]
    assert [edge["sort_order"] for edge in edges] == [0, 1, 2]
    assert result["changes"]["created"] == [inserted["id"]]


def test_checkpoint_hints_preserve_shifted_duplicate_function_jids(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(
        1,
        {"name": "Shifted Duplicate Functions", "template_source": "{{ section }}"},
    )
    section = document["sections"][0]
    service.save(
        1,
        {
            "resource_id": section["id"],
            "content": "{{ helper() }}\n{{ helper() }}",
        },
    )
    current = _document(service.state(1), document["id"])
    original_first, original_second = current["sections"][0]["functions"]

    source = "{{ helper() }}\n{{ helper() }}\n{{ helper() }}"
    result = service.checkpoint(
        1,
        {
            "resource_id": section["id"],
            "content": source,
            "reference_bindings": [
                {
                    "reference_id": original_first["reference_id"],
                    "start": 18,
                    "end": 24,
                    "symbol": "helper",
                },
                {
                    "reference_id": original_second["reference_id"],
                    "start": 33,
                    "end": 39,
                    "symbol": "helper",
                },
            ],
        },
    )

    current = _document(result["state"], document["id"])
    inserted, first, second = current["sections"][0]["functions"]
    assert inserted["id"] not in {original_first["id"], original_second["id"]}
    assert first["id"] == original_first["id"]
    assert first["reference_id"] == original_first["reference_id"]
    assert second["id"] == original_second["id"]
    assert second["reference_id"] == original_second["reference_id"]

    edges = repository.list_edges(1, section["id"])
    assert [edge["id"] for edge in edges] == [
        inserted["reference_id"],
        original_first["reference_id"],
        original_second["reference_id"],
    ]
    assert [edge["sort_order"] for edge in edges] == [0, 1, 2]
