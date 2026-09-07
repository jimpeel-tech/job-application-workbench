from __future__ import annotations

from pathlib import Path

import pytest

from jaw.application.document_workbench_resource_service import (
    delete_unreferenced_resource,
    rename_reference_symbol,
)
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase

_TEST_TEMPLATE = r"""\documentclass[10pt,letterpaper]{article}
\begin{document}
{{ section }}
\end{document}
"""


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


def _workspace(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    document = service.create_document(
        1,
        {"name": "Resume", "template_source": _TEST_TEMPLATE},
    )
    return database, service, document


def test_rename_reference_preserves_resource_identity_and_clean_save_state(tmp_path: Path) -> None:
    database, service, document = _workspace(tmp_path)
    repository = database.document_workbench_repository
    template = document["template"]
    section = document["sections"][0]

    result = rename_reference_symbol(
        repository,
        1,
        {
            "parent_id": document["id"],
            "child_id": section["id"],
            "symbol": "experience",
        },
    )

    edge = repository.find_edge_symbol(1, document["id"], "experience")
    assert edge is not None
    assert edge["child_id"] == section["id"]
    assert repository.find_edge_symbol(1, document["id"], "section") is None
    updated_section = repository.require_resource(1, section["id"])
    assert updated_section["id"] == section["id"]
    assert updated_section["symbol"] == "experience"
    assert updated_section["name"] == ""
    updated_template = repository.require_resource(1, template["id"])
    assert "{{ experience }}" in updated_template["content"]
    assert repository.get_buffer(1, template["id"]) is None
    assert result["source_dirty"] is False


def test_rename_reference_keeps_dirty_template_dirty(tmp_path: Path) -> None:
    database, service, document = _workspace(tmp_path)
    repository = database.document_workbench_repository
    template = document["template"]
    section = document["sections"][0]
    dirty = template["content"].replace("\\begin{document}", "\\begin{document}\n% unsaved")
    service.checkpoint(
        1,
        {
            "resource_id": template["id"],
            "document_id": document["id"],
            "content": dirty,
            "cursor_start": 20,
            "cursor_end": 20,
        },
    )

    result = rename_reference_symbol(
        repository,
        1,
        {
            "parent_id": document["id"],
            "child_id": section["id"],
            "symbol": "summary",
        },
    )

    canonical = repository.require_resource(1, template["id"])
    buffer = repository.get_buffer(1, template["id"])
    assert canonical["content"] == template["content"]
    assert buffer is not None
    assert "% unsaved" in buffer["content"]
    assert "{{ summary }}" in buffer["content"]
    assert result["source_dirty"] is True


def test_rename_reference_updates_all_documents_using_shared_template(tmp_path: Path) -> None:
    database, service, first = _workspace(tmp_path)
    repository = database.document_workbench_repository
    second = service.create_document(1, {"name": "Second"})
    service.update_resource(
        1,
        {"resource_id": second["id"], "template_id": first["template"]["id"]},
    )
    shared = service.state(1)
    first_state = next(item for item in shared["documents"] if item["id"] == first["id"])
    second_state = next(item for item in shared["documents"] if item["id"] == second["id"])
    first_section = first_state["sections"][0]
    second_section = second_state["sections"][0]

    result = rename_reference_symbol(
        repository,
        1,
        {
            "parent_id": first["id"],
            "child_id": first_section["id"],
            "symbol": "profile",
        },
    )

    assert set(result["affected_parent_ids"]) == {first["id"], second["id"]}
    assert repository.find_edge_symbol(1, first["id"], "profile")["child_id"] == first_section["id"]
    assert repository.find_edge_symbol(1, second["id"], "profile")["child_id"] == second_section["id"]


def test_rename_reference_rejects_reserved_but_allows_duplicate_symbols(tmp_path: Path) -> None:
    database, service, document = _workspace(tmp_path)
    repository = database.document_workbench_repository
    first = document["sections"][0]
    template = document["template"]
    source = template["content"].replace("{{ section }}", "{{ section }}\n{{ other }}")
    service.checkpoint(
        1,
        {"resource_id": template["id"], "document_id": document["id"], "content": source},
    )
    other = next(
        item
        for item in service.state(1)["documents"][0]["sections"]
        if item["reference_symbol"] == "other"
    )

    with pytest.raises(ValueError, match="reserved"):
        rename_reference_symbol(
            repository,
            1,
            {"parent_id": document["id"], "child_id": first["id"], "symbol": "user"},
        )

    result = rename_reference_symbol(
        repository,
        1,
        {
            "parent_id": document["id"],
            "child_id": first["id"],
            "symbol": other["reference_symbol"],
        },
    )
    duplicate_edges = repository.find_edges_symbol(1, document["id"], "other")
    assert result["new_symbol"] == "other"
    assert len(duplicate_edges) == 2
    assert {edge["child_id"] for edge in duplicate_edges} == {first["id"], other["id"]}
    assert len({edge["id"] for edge in duplicate_edges}) == 2


def test_delete_staged_section_cascades_private_children_but_preserves_globals(tmp_path: Path) -> None:
    database, service, document = _workspace(tmp_path)
    repository = database.document_workbench_repository
    section = document["sections"][0]

    service.save(1, {"resource_id": section["id"], "content": "{{ local_fn }}"})
    section_state = next(
        item
        for item in service.state(1)["documents"][0]["sections"]
        if item["id"] == section["id"]
    )
    private_function = section_state["functions"][0]
    global_function = repository.create_resource(
        1,
        "function",
        name="Global Helper",
        symbol="global_helper",
        visibility="global",
        content="global",
    )
    repository.link(
        1,
        section["id"],
        global_function["id"],
        edge_kind="function",
        symbol="global_helper",
    )

    # Staging is explicit now; checkpointing source never detaches resources.
    repository.unlink(1, document["id"], section["id"])
    repository.update_resource(1, section["id"], state="orphaned")

    result = delete_unreferenced_resource(
        repository, 1, {"resource_id": section["id"]}
    )

    assert section["id"] in result["deleted"]
    assert private_function["id"] in result["deleted"]
    assert repository.get_resource(1, section["id"]) is None
    assert repository.get_resource(1, private_function["id"]) is None
    assert repository.get_resource(1, global_function["id"]) is not None


def test_template_delete_is_blocked_while_used_and_allowed_when_unused(tmp_path: Path) -> None:
    database, service, document = _workspace(tmp_path)
    repository = database.document_workbench_repository
    template = document["template"]

    with pytest.raises(ValueError, match="used by 1 Document"):
        delete_unreferenced_resource(repository, 1, {"resource_id": template["id"]})

    replacement = repository.create_resource(
        1,
        "template",
        name="Replacement",
        symbol="template",
        visibility="global",
        content=template["content"],
        settings={"renderer": "tectonic", "format": "latex_jinja"},
    )
    service.update_resource(
        1,
        {"resource_id": document["id"], "template_id": replacement["id"]},
    )

    result = delete_unreferenced_resource(repository, 1, {"resource_id": template["id"]})
    assert template["id"] in result["deleted"]
    assert repository.get_resource(1, template["id"]) is None


def test_document_delete_removes_private_tree_and_preserves_global_resources(tmp_path: Path) -> None:
    database, service, document = _workspace(tmp_path)
    repository = database.document_workbench_repository
    template = document["template"]
    section = document["sections"][0]
    service.save(1, {"resource_id": section["id"], "content": "{{ local_fn }}"})
    private_function = service.state(1)["documents"][0]["sections"][0]["functions"][0]
    global_function = repository.create_resource(
        1,
        "function",
        name="Global Helper",
        symbol="global_helper",
        visibility="global",
        content="global",
    )
    repository.link(
        1,
        section["id"],
        global_function["id"],
        edge_kind="function",
        symbol="global_helper",
    )

    result = delete_unreferenced_resource(repository, 1, {"resource_id": document["id"]})

    assert document["id"] in result["deleted"]
    assert template["id"] in result["deleted"]
    assert section["id"] in result["deleted"]
    assert private_function["id"] in result["deleted"]
    assert repository.get_document(1, document["id"]) is None
    assert repository.get_resource(1, global_function["id"]) is not None
