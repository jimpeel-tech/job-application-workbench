from __future__ import annotations

from pathlib import Path

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


def _share_first_template(database, service, first: dict, second: dict) -> tuple[dict, dict]:
    repository = database.document_workbench_repository
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
    return _document(state, first["id"]), _document(state, second["id"])


def test_checkpointing_shared_global_template_reconciles_every_document_graph(
    tmp_path: Path,
) -> None:
    database, service = _service(tmp_path)
    first = service.create_document(
        1,
        {"name": "First", "template_source": "{{ body }}"},
    )
    second = service.create_document(1, {"name": "Second"})
    first, second = _share_first_template(database, service, first, second)

    first_body = first["sections"][0]
    second_body = second["sections"][0]
    assert first_body["reference_symbol"] == second_body["reference_symbol"] == "body"
    assert first_body["id"] != second_body["id"]
    assert first_body["reference_id"] != second_body["reference_id"]

    result = service.checkpoint(
        1,
        {
            "resource_id": first["template_id"],
            "document_id": first["id"],
            "content": "{{ body }}\n{{ extra }}",
        },
    )

    current_first = _document(result["state"], first["id"])
    current_second = _document(result["state"], second["id"])
    assert current_first["template_id"] == current_second["template_id"] == first["template_id"]
    assert current_first["template"]["dirty"] is True
    assert current_second["template"]["dirty"] is True
    assert current_first["template"]["editor_content"] == "{{ body }}\n{{ extra }}"
    assert current_second["template"]["editor_content"] == "{{ body }}\n{{ extra }}"

    assert [item["reference_symbol"] for item in current_first["sections"]] == ["body", "extra"]
    assert [item["reference_symbol"] for item in current_second["sections"]] == ["body", "extra"]
    assert current_first["sections"][0]["id"] == first_body["id"]
    assert current_first["sections"][0]["reference_id"] == first_body["reference_id"]
    assert current_second["sections"][0]["id"] == second_body["id"]
    assert current_second["sections"][0]["reference_id"] == second_body["reference_id"]

    first_extra = current_first["sections"][1]
    second_extra = current_second["sections"][1]
    assert first_extra["id"] != second_extra["id"]
    assert first_extra["reference_id"] != second_extra["reference_id"]
    assert first_extra["visibility"] == second_extra["visibility"] == "private"
    assert first_extra["owner_id"] == first["id"]
    assert second_extra["owner_id"] == second["id"]
    assert set(result["changes"]["created"]) == {first_extra["id"], second_extra["id"]}


def test_duplicate_insertion_hints_propagate_across_shared_template_document_graphs(
    tmp_path: Path,
) -> None:
    database, service = _service(tmp_path)
    first = service.create_document(
        1,
        {"name": "First", "template_source": "{{ body }}\n{{ body }}"},
    )
    second = service.create_document(1, {"name": "Second"})
    first, second = _share_first_template(database, service, first, second)

    first_before = list(first["sections"])
    second_before = list(second["sections"])
    assert len(first_before) == len(second_before) == 2

    source = "{{ body }}\n{{ body }}\n{{ body }}"
    result = service.checkpoint(
        1,
        {
            "resource_id": first["template_id"],
            "document_id": first["id"],
            "content": source,
            "reference_bindings": [
                {
                    "reference_id": first_before[0]["reference_id"],
                    "start": 14,
                    "end": 18,
                    "symbol": "body",
                },
                {
                    "reference_id": first_before[1]["reference_id"],
                    "start": 25,
                    "end": 29,
                    "symbol": "body",
                },
            ],
        },
    )

    current_first = _document(result["state"], first["id"])
    current_second = _document(result["state"], second["id"])
    first_after = current_first["sections"]
    second_after = current_second["sections"]

    assert len(first_after) == len(second_after) == 3
    assert first_after[1]["id"] == first_before[0]["id"]
    assert first_after[1]["reference_id"] == first_before[0]["reference_id"]
    assert first_after[2]["id"] == first_before[1]["id"]
    assert first_after[2]["reference_id"] == first_before[1]["reference_id"]

    # The active Document's positional hints describe shared Template occurrence
    # identity. JAW translates those hints to the corresponding per-Document
    # ref_* JIDs rather than letting text-only matching shift a different graph.
    assert second_after[1]["id"] == second_before[0]["id"]
    assert second_after[1]["reference_id"] == second_before[0]["reference_id"]
    assert second_after[2]["id"] == second_before[1]["id"]
    assert second_after[2]["reference_id"] == second_before[1]["reference_id"]

    assert first_after[0]["id"] not in {item["id"] for item in first_before}
    assert second_after[0]["id"] not in {item["id"] for item in second_before}
    assert first_after[0]["reference_id"] not in {
        item["reference_id"] for item in first_before
    }
    assert second_after[0]["reference_id"] not in {
        item["reference_id"] for item in second_before
    }
