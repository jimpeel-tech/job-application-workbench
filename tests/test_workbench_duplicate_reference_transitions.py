from __future__ import annotations

from pathlib import Path

import pytest

from jaw.application.document_workbench_application import DocumentWorkbenchApplication
from jaw.database import JobDatabase


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {
            "active_user_id": user_id or 1,
            "user": {"first_name": "Jane", "last_name": "Engineer"},
        }


def _app(tmp_path: Path) -> tuple[JobDatabase, DocumentWorkbenchApplication]:
    database = JobDatabase(tmp_path / "jaw.db")
    return database, DocumentWorkbenchApplication(database, _UserData())


def _document(state: dict, document_id: str) -> dict:
    return next(item for item in state["documents"] if item["id"] == document_id)


def test_remove_one_of_two_global_references_keeps_other_reference_and_resource(
    tmp_path: Path,
) -> None:
    database, app = _app(tmp_path)
    repository = database.document_workbench_repository

    document = app.create_document(
        1,
        {
            "name": "Repeated Global",
            "template_source": "{{ placeholder }}\n{{ placeholder }}",
        },
    )
    private_sections = document["sections"]
    assert len(private_sections) == 2

    # Replace the two automatically-created private bindings with two durable
    # references to one Global Section. Reusing a resource JID is Global-only.
    for section in private_sections:
        reference_id = section["reference_id"]
        repository.unlink_reference(1, reference_id)
        repository.delete_resource(1, section["id"])

    shared = repository.create_resource(
        1,
        "section",
        symbol="placeholder",
        visibility="global",
        content="Shared body",
        settings={"content_shape": "paragraphs"},
    )
    first = repository.link(
        1,
        document["id"],
        shared["id"],
        edge_kind="section",
        symbol="placeholder",
        sort_order=0,
    )
    second = repository.link(
        1,
        document["id"],
        shared["id"],
        edge_kind="section",
        symbol="placeholder",
        sort_order=1,
    )
    assert first["id"] != second["id"]

    result = app.transition_reference(
        1,
        {
            "action": "remove",
            "reference_id": first["id"],
            "parent_id": document["id"],
            "child_id": shared["id"],
            "source_content": "{{ placeholder }}",
            "disposition": "remove",
        },
    )

    remaining = repository.list_edges(1, document["id"])
    assert [edge["id"] for edge in remaining] == [second["id"]]
    assert remaining[0]["child_id"] == shared["id"]
    assert remaining[0]["symbol"] == "placeholder"

    preserved = repository.require_resource(1, shared["id"])
    assert preserved["visibility"] == "global"
    assert preserved["state"] == "active"

    current = _document(result["state"], document["id"])
    assert len(current["sections"]) == 1
    assert current["sections"][0]["id"] == shared["id"]
    assert current["sections"][0]["reference_id"] == second["id"]
    assert current["sections"][0]["reference_symbol"] == "placeholder"
    assert result["old_still_referenced"] is True
    assert result["removed_reference_ids"] == [first["id"]]


def test_private_resource_jid_cannot_be_referenced_twice(tmp_path: Path) -> None:
    database, app = _app(tmp_path)
    repository = database.document_workbench_repository
    document = app.create_document(
        1,
        {
            "name": "Repeated Private",
            "template_source": "{{ section }}",
        },
    )
    section = document["sections"][0]

    with pytest.raises(ValueError, match="make the resource Global before reusing it"):
        repository.link(
            1,
            document["id"],
            section["id"],
            edge_kind="section",
            symbol="section",
            sort_order=1,
        )

    edges = repository.list_edges(1, document["id"])
    assert len(edges) == 1
    assert edges[0]["id"] == section["reference_id"]
    assert edges[0]["child_id"] == section["id"]
