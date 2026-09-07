from __future__ import annotations

from pathlib import Path

from jaw.application.document_workbench_resource_service import rename_reference_symbol
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def test_renaming_one_repeated_global_reference_changes_only_that_ref_jid(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(
        1,
        {
            "name": "Global Aliases",
            "template_source": "{{ shared }}|{{ shared }}",
        },
    )

    # Replace the independently-created private Sections with two references to
    # one Global resource JID, matching drag/drop reuse semantics.
    for section in document["sections"]:
        repository.unlink_reference(1, section["reference_id"])
        repository.delete_resource(1, section["id"])
    shared = repository.create_resource(
        1,
        "section",
        symbol="shared",
        visibility="global",
        content="Shared body",
        settings={"content_shape": "paragraphs"},
    )
    first = repository.link(
        1,
        document["id"],
        shared["id"],
        edge_kind="section",
        symbol="shared",
        sort_order=0,
    )
    second = repository.link(
        1,
        document["id"],
        shared["id"],
        edge_kind="section",
        symbol="shared",
        sort_order=1,
    )

    result = rename_reference_symbol(
        repository,
        1,
        {
            "reference_id": first["id"],
            "parent_id": document["id"],
            "child_id": shared["id"],
            "symbol": "intro",
        },
    )

    edges = repository.list_edges(1, document["id"])
    assert [edge["id"] for edge in edges] == [first["id"], second["id"]]
    assert [edge["symbol"] for edge in edges] == ["intro", "shared"]
    assert all(edge["child_id"] == shared["id"] for edge in edges)
    assert repository.require_resource(1, shared["id"])["symbol"] == "shared"
    template = repository.require_resource(1, document["template_id"])
    assert template["content"] == "{{ intro }}|{{ shared }}"
    assert result["affected_reference_ids"] == [first["id"]]
    assert result["affected_resource_ids"] == [shared["id"]]


def test_renaming_second_private_duplicate_preserves_first_reference_identity(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(
        1,
        {
            "name": "Private Duplicates",
            "template_source": "{{ section }}|{{ section }}",
        },
    )
    first, second = document["sections"]

    result = rename_reference_symbol(
        repository,
        1,
        {
            "reference_id": second["reference_id"],
            "parent_id": document["id"],
            "child_id": second["id"],
            "symbol": "experience",
        },
    )

    edges = repository.list_edges(1, document["id"])
    assert edges[0]["id"] == first["reference_id"]
    assert edges[0]["child_id"] == first["id"]
    assert edges[0]["symbol"] == "section"
    assert edges[1]["id"] == second["reference_id"]
    assert edges[1]["child_id"] == second["id"]
    assert edges[1]["symbol"] == "experience"
    assert repository.require_resource(1, first["id"])["symbol"] == "section"
    assert repository.require_resource(1, second["id"])["symbol"] == "experience"
    template = repository.require_resource(1, document["template_id"])
    assert template["content"] == "{{ section }}|{{ experience }}"
    assert result["reference_id"] == second["reference_id"]


def test_renaming_one_repeated_global_function_changes_only_that_ref_jid(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(1, {"name": "Global Function Aliases"})
    section = document["sections"][0]
    service.save(1, {"resource_id": section["id"], "content": "{{ shared }}|{{ shared }}"})
    current = next(
        item for item in service.state(1)["documents"] if item["id"] == document["id"]
    )

    for function in current["sections"][0]["functions"]:
        repository.unlink_reference(1, function["reference_id"])
        repository.delete_resource(1, function["id"])
    shared = repository.create_resource(
        1,
        "function",
        symbol="shared",
        visibility="global",
        content="Shared helper",
    )
    first = repository.link(
        1,
        section["id"],
        shared["id"],
        edge_kind="function",
        symbol="shared",
        sort_order=0,
    )
    second = repository.link(
        1,
        section["id"],
        shared["id"],
        edge_kind="function",
        symbol="shared",
        sort_order=1,
    )

    result = rename_reference_symbol(
        repository,
        1,
        {
            "reference_id": second["id"],
            "parent_id": section["id"],
            "child_id": shared["id"],
            "symbol": "formatter",
        },
    )

    edges = repository.list_edges(1, section["id"])
    assert [edge["id"] for edge in edges] == [first["id"], second["id"]]
    assert [edge["symbol"] for edge in edges] == ["shared", "formatter"]
    assert all(edge["child_id"] == shared["id"] for edge in edges)
    assert repository.require_resource(1, shared["id"])["symbol"] == "shared"
    saved_section = repository.require_resource(1, section["id"])
    assert saved_section["content"] == "{{ shared }}|{{ formatter }}"
    assert result["affected_reference_ids"] == [second["id"]]


def test_renaming_second_private_function_duplicate_preserves_first_identity(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(1, {"name": "Private Function Duplicates"})
    section = document["sections"][0]
    service.save(1, {"resource_id": section["id"], "content": "{{ helper }}|{{ helper }}"})
    current = next(
        item for item in service.state(1)["documents"] if item["id"] == document["id"]
    )
    first, second = current["sections"][0]["functions"]

    result = rename_reference_symbol(
        repository,
        1,
        {
            "reference_id": second["reference_id"],
            "parent_id": section["id"],
            "child_id": second["id"],
            "symbol": "formatter",
        },
    )

    edges = repository.list_edges(1, section["id"])
    assert edges[0]["id"] == first["reference_id"]
    assert edges[0]["child_id"] == first["id"]
    assert edges[0]["symbol"] == "helper"
    assert edges[1]["id"] == second["reference_id"]
    assert edges[1]["child_id"] == second["id"]
    assert edges[1]["symbol"] == "formatter"
    assert repository.require_resource(1, first["id"])["symbol"] == "helper"
    assert repository.require_resource(1, second["id"])["symbol"] == "formatter"
    saved_section = repository.require_resource(1, section["id"])
    assert saved_section["content"] == "{{ helper }}|{{ formatter }}"
    assert result["reference_id"] == second["reference_id"]
