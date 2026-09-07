from __future__ import annotations

from pathlib import Path

from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def _document(state: dict, document_id: str) -> dict:
    return next(item for item in state["documents"] if item["id"] == document_id)


def _shared(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    repository = database.document_workbench_repository
    first = service.create_document(
        1,
        {"name": "First", "template_source": "{{ body }}"},
    )
    second = service.create_document(1, {"name": "Second"})
    repository.update_resource(
        1,
        first["template_id"],
        visibility="global",
        state="active",
        owner_id=None,
    )
    service.update_resource(
        1,
        {"resource_id": second["id"], "template_id": first["template_id"]},
    )
    state = service.state(1)
    return (
        database,
        service,
        _document(state, first["id"]),
        _document(state, second["id"]),
    )


def test_direct_save_of_shared_template_reconciles_all_document_graphs(tmp_path: Path) -> None:
    _, service, first, second = _shared(tmp_path)
    first_body = first["sections"][0]
    second_body = second["sections"][0]

    saved = service.save(
        1,
        {
            "resource_id": first["template_id"],
            "document_id": first["id"],
            "content": "{{ body }}\n{{ closing }}",
        },
    )

    current_first = _document(saved["state"], first["id"])
    current_second = _document(saved["state"], second["id"])
    assert current_first["template"]["dirty"] is False
    assert current_second["template"]["dirty"] is False
    assert current_first["template"]["content"] == "{{ body }}\n{{ closing }}"
    assert current_second["template"]["content"] == "{{ body }}\n{{ closing }}"
    assert [item["reference_symbol"] for item in current_first["sections"]] == ["body", "closing"]
    assert [item["reference_symbol"] for item in current_second["sections"]] == ["body", "closing"]
    assert current_first["sections"][0]["id"] == first_body["id"]
    assert current_first["sections"][0]["reference_id"] == first_body["reference_id"]
    assert current_second["sections"][0]["id"] == second_body["id"]
    assert current_second["sections"][0]["reference_id"] == second_body["reference_id"]
    assert len(saved["changes"]["created"]) == 2


def test_saving_checkpointed_shared_template_does_not_create_second_set_of_sections(
    tmp_path: Path,
) -> None:
    _, service, first, second = _shared(tmp_path)
    source = "{{ body }}\n{{ closing }}"
    checkpoint = service.checkpoint(
        1,
        {
            "resource_id": first["template_id"],
            "document_id": first["id"],
            "content": source,
        },
    )
    checkpoint_first = _document(checkpoint["state"], first["id"])
    checkpoint_second = _document(checkpoint["state"], second["id"])
    first_ids = [item["id"] for item in checkpoint_first["sections"]]
    second_ids = [item["id"] for item in checkpoint_second["sections"]]
    first_refs = [item["reference_id"] for item in checkpoint_first["sections"]]
    second_refs = [item["reference_id"] for item in checkpoint_second["sections"]]

    saved = service.save(
        1,
        {
            "resource_id": first["template_id"],
            "document_id": first["id"],
            "content": source,
        },
    )

    current_first = _document(saved["state"], first["id"])
    current_second = _document(saved["state"], second["id"])
    assert [item["id"] for item in current_first["sections"]] == first_ids
    assert [item["id"] for item in current_second["sections"]] == second_ids
    assert [item["reference_id"] for item in current_first["sections"]] == first_refs
    assert [item["reference_id"] for item in current_second["sections"]] == second_refs
    assert current_first["template"]["dirty"] is False
    assert current_second["template"]["dirty"] is False
    assert saved["changes"] == {"created": [], "orphaned": [], "deleted": []}
