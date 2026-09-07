from __future__ import annotations

from pathlib import Path

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


def test_single_use_global_template_becomes_private_in_place(tmp_path: Path) -> None:
    database, app = _app(tmp_path)
    document = app.create_document(
        1,
        {"name": "Resume", "template_source": "{{ body }}"},
    )
    template_id = document["template_id"]
    section_id = document["sections"][0]["id"]

    made_global = app.update_resource(
        1,
        {"resource_id": template_id, "visibility": "global"},
    )
    global_template = database.document_workbench_repository.require_resource(1, template_id)
    assert made_global["resource"]["id"] == template_id
    assert global_template["visibility"] == "global"
    assert global_template["owner_id"] is None

    result = app.update_resource(
        1,
        {
            "resource_id": template_id,
            "visibility": "private",
            "owner_id": document["id"],
        },
    )

    assert result["resource"]["id"] == template_id
    assert result["resource"]["visibility"] == "private"
    assert result["resource"]["owner_id"] == document["id"]
    assert result["template_detached"] is None

    current = _document(result["state"], document["id"])
    assert current["template_id"] == template_id
    assert current["template"]["id"] == template_id
    assert current["template"]["visibility"] == "private"
    assert current["template"]["owner_id"] == document["id"]
    assert [item["id"] for item in current["sections"]] == [section_id]


def test_shared_global_template_detaches_private_copy_for_selected_document(
    tmp_path: Path,
) -> None:
    database, app = _app(tmp_path)
    first = app.create_document(
        1,
        {"name": "First", "template_source": "{{ body }}"},
    )
    second = app.create_document(
        1,
        {"name": "Second", "template_source": "{{ body }}"},
    )
    shared_template_id = first["template_id"]
    first_section_id = first["sections"][0]["id"]

    app.update_resource(
        1,
        {"resource_id": shared_template_id, "visibility": "global"},
    )
    assigned = app.update_resource(
        1,
        {"resource_id": second["id"], "template_id": shared_template_id},
    )
    shared_state = assigned["state"]
    first_shared = _document(shared_state, first["id"])
    second_shared = _document(shared_state, second["id"])
    second_section_id = second_shared["sections"][0]["id"]

    assert first_shared["template_id"] == second_shared["template_id"] == shared_template_id
    assert first_shared["template"]["visibility"] == "global"
    assert first_section_id != second_section_id

    result = app.update_resource(
        1,
        {
            "resource_id": shared_template_id,
            "visibility": "private",
            "owner_id": first["id"],
        },
    )

    detached = result["template_detached"]
    assert detached is not None
    assert detached["global_template_id"] == shared_template_id
    assert detached["document_id"] == first["id"]
    private_template_id = detached["private_template_id"]
    assert private_template_id != shared_template_id
    assert result["resource"]["id"] == private_template_id
    assert result["resource"]["visibility"] == "private"
    assert result["resource"]["owner_id"] == first["id"]

    state = result["state"]
    first_private = _document(state, first["id"])
    second_global = _document(state, second["id"])
    assert first_private["template_id"] == private_template_id
    assert first_private["template"]["visibility"] == "private"
    assert first_private["template"]["owner_id"] == first["id"]
    assert second_global["template_id"] == shared_template_id
    assert second_global["template"]["visibility"] == "global"
    assert second_global["template"]["owner_id"] is None

    repository = database.document_workbench_repository
    global_template = repository.require_resource(1, shared_template_id)
    private_template = repository.require_resource(1, private_template_id)
    assert private_template["content"] == global_template["content"] == "{{ body }}"
    assert [item["id"] for item in first_private["sections"]] == [first_section_id]
    assert [item["id"] for item in second_global["sections"]] == [second_section_id]


def test_assigning_private_template_to_second_document_promotes_it_to_global(
    tmp_path: Path,
) -> None:
    _, app = _app(tmp_path)
    first = app.create_document(
        1,
        {"name": "First", "template_source": "{{ body }}"},
    )
    second = app.create_document(
        1,
        {"name": "Second", "template_source": "{{ body }}"},
    )

    result = app.update_resource(
        1,
        {"resource_id": second["id"], "template_id": first["template_id"]},
    )

    first_state = _document(result["state"], first["id"])
    second_state = _document(result["state"], second["id"])
    assert first_state["template_id"] == second_state["template_id"] == first["template_id"]
    assert first_state["template"]["visibility"] == "global"
    assert first_state["template"]["owner_id"] is None


def test_switching_document_template_stages_sections_not_used_by_new_template(
    tmp_path: Path,
) -> None:
    database, app = _app(tmp_path)
    first = app.create_document(
        1,
        {"name": "First", "template_source": "{{ body }}"},
    )
    second = app.create_document(1, {"name": "Second"})
    stale_section = second["sections"][0]
    assert stale_section["reference_symbol"] == "section"

    result = app.update_resource(
        1,
        {"resource_id": second["id"], "template_id": first["template_id"]},
    )

    current = _document(result["state"], second["id"])
    assert [item["reference_symbol"] for item in current["sections"]] == ["body"]
    assert all(item["id"] != stale_section["id"] for item in current["sections"])

    repository = database.document_workbench_repository
    staged = repository.require_resource(1, stale_section["id"])
    assert staged["state"] == "orphaned"
    assert staged["visibility"] == "private"
    assert staged["owner_id"] == second["id"]
    assert stale_section["id"] in {item["id"] for item in result["state"]["orphans"]}
    assert all(
        edge["child_id"] != stale_section["id"]
        for edge in repository.list_edges(1, second["id"])
    )
