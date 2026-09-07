from __future__ import annotations

from pathlib import Path

import pytest

from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def _service(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    return database, service


def test_dragging_same_global_section_twice_creates_two_reference_jids(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    repository = database.document_workbench_repository
    document = service.create_document(1, {"name": "Global Reuse"})
    shared = repository.create_resource(
        1,
        "section",
        symbol="shared",
        visibility="global",
        content="Shared body",
        settings={"content_shape": "paragraphs"},
    )

    first = service.link_existing(
        1,
        {"parent_id": document["id"], "child_id": shared["id"]},
    )
    second = service.link_existing(
        1,
        {"parent_id": document["id"], "child_id": shared["id"]},
    )

    assert first["resource_id"] == second["resource_id"] == shared["id"]
    assert first["reference_id"] != second["reference_id"]
    assert first["insertion"] == second["insertion"] == "{{ shared }}"
    repeated = [
        edge
        for edge in repository.list_edges(1, document["id"])
        if edge["child_id"] == shared["id"]
    ]
    assert [edge["id"] for edge in repeated] == [
        first["reference_id"],
        second["reference_id"],
    ]


def test_dragging_same_private_section_twice_requires_global_visibility(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    repository = database.document_workbench_repository
    document = service.create_document(1, {"name": "Private Reuse"})
    section = document["sections"][0]

    with pytest.raises(ValueError, match="make the resource Global before reusing it"):
        service.link_existing(
            1,
            {"parent_id": document["id"], "child_id": section["id"]},
        )

    references = [
        edge
        for edge in repository.list_edges(1, document["id"])
        if edge["child_id"] == section["id"]
    ]
    assert len(references) == 1
    assert references[0]["id"] == section["reference_id"]


def test_dragging_same_global_function_twice_creates_two_reference_jids(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    repository = database.document_workbench_repository
    document = service.create_document(1, {"name": "Global Function Reuse"})
    section = document["sections"][0]
    shared = repository.create_resource(
        1,
        "function",
        symbol="shared_helper",
        visibility="global",
        content="Shared helper body",
    )

    first = service.link_existing(
        1,
        {"parent_id": section["id"], "child_id": shared["id"]},
    )
    second = service.link_existing(
        1,
        {"parent_id": section["id"], "child_id": shared["id"]},
    )

    assert first["resource_id"] == second["resource_id"] == shared["id"]
    assert first["reference_id"] != second["reference_id"]
    assert first["insertion"] == second["insertion"] == "{{ shared_helper }}"
    repeated = [
        edge
        for edge in repository.list_edges(1, section["id"])
        if edge["child_id"] == shared["id"]
    ]
    assert [edge["id"] for edge in repeated] == [
        first["reference_id"],
        second["reference_id"],
    ]


def test_dragging_same_private_function_twice_requires_global_visibility(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    repository = database.document_workbench_repository
    document = service.create_document(1, {"name": "Private Function Reuse"})
    section = document["sections"][0]
    service.save(1, {"resource_id": section["id"], "content": "{{ helper }}"})
    current = next(
        item for item in service.state(1)["documents"] if item["id"] == document["id"]
    )
    helper = current["sections"][0]["functions"][0]

    with pytest.raises(ValueError, match="make the resource Global before reusing it"):
        service.link_existing(
            1,
            {"parent_id": section["id"], "child_id": helper["id"]},
        )

    references = [
        edge
        for edge in repository.list_edges(1, section["id"])
        if edge["child_id"] == helper["id"]
    ]
    assert len(references) == 1
    assert references[0]["id"] == helper["reference_id"]


def test_staged_private_section_can_move_and_keep_its_resource_jid(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    repository = database.document_workbench_repository
    source = service.create_document(1, {"name": "Source"})
    target = service.create_document(1, {"name": "Target"})
    section = source["sections"][0]

    repository.unlink_reference(1, section["reference_id"])
    repository.update_resource(1, section["id"], state="orphaned")

    linked = service.link_existing(
        1,
        {"parent_id": target["id"], "child_id": section["id"]},
    )

    assert linked["resource_id"] == section["id"]
    assert linked["reference_id"] != section["reference_id"]
    moved = repository.require_resource(1, section["id"])
    assert moved["visibility"] == "private"
    assert moved["state"] == "active"
    assert moved["owner_id"] == target["id"]


def test_staged_private_function_can_move_and_keep_its_resource_jid(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    repository = database.document_workbench_repository
    source = service.create_document(1, {"name": "Source"})
    target = service.create_document(1, {"name": "Target"})
    source_section = source["sections"][0]
    target_section = target["sections"][0]
    service.save(1, {"resource_id": source_section["id"], "content": "{{ helper }}"})
    source_state = next(
        item for item in service.state(1)["documents"] if item["id"] == source["id"]
    )
    helper = source_state["sections"][0]["functions"][0]

    repository.unlink_reference(1, helper["reference_id"])
    repository.update_resource(1, helper["id"], state="orphaned")

    linked = service.link_existing(
        1,
        {"parent_id": target_section["id"], "child_id": helper["id"]},
    )

    assert linked["resource_id"] == helper["id"]
    assert linked["reference_id"] != helper["reference_id"]
    moved = repository.require_resource(1, helper["id"])
    assert moved["visibility"] == "private"
    assert moved["state"] == "active"
    assert moved["owner_id"] == target_section["id"]
