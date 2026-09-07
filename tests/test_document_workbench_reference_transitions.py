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


def _private_document(app: DocumentWorkbenchApplication) -> dict:
    return app.create_document(
        1,
        {
            "name": "Resume",
            "template_source": "{{ section }}",
        },
    )


def test_update_preserves_section_identity_content_and_children(tmp_path: Path) -> None:
    _, app = _app(tmp_path)
    document = _private_document(app)
    section = document["sections"][0]
    app.save(
        1,
        {"resource_id": section["id"], "content": "{{ helper }}\nSection body"},
    )
    current = _document(app.state(1), document["id"])
    helper = current["sections"][0]["functions"][0]
    app.save(1, {"resource_id": helper["id"], "content": "Helper body"})

    result = app.transition_reference(
        1,
        {
            "action": "update",
            "parent_id": document["id"],
            "child_id": section["id"],
            "symbol": "experience",
            "source_content": "{{ experience }}",
            "cursor_start": 8,
            "cursor_end": 8,
        },
    )

    current = _document(result["state"], document["id"])
    renamed = current["sections"][0]
    assert renamed["id"] == section["id"]
    assert renamed["reference_symbol"] == "experience"
    assert renamed["symbol"] == "experience"
    assert renamed["name"] == ""
    assert renamed["editor_content"] == "{{ helper }}\nSection body"
    assert [item["id"] for item in renamed["functions"]] == [helper["id"]]
    assert renamed["functions"][0]["editor_content"] == "Helper body"
    assert result["state"]["orphans"] == []


def test_update_resolves_symbol_from_valid_jinja_when_editor_hint_is_not_identifier(
    tmp_path: Path,
) -> None:
    _, app = _app(tmp_path)
    document = _private_document(app)
    section = document["sections"][0]
    app.save(
        1,
        {
            "resource_id": section["id"],
            "content": "{% for item in accomplishments() %}{{ item }}{% endfor %}",
        },
    )
    current = _document(app.state(1), document["id"])
    function = current["sections"][0]["functions"][0]

    source = "{% for item in achievements() %}{{ item }}{% endfor %}"
    result = app.transition_reference(
        1,
        {
            "action": "update",
            "parent_id": section["id"],
            "child_id": function["id"],
            # A tracked editor range can include punctuation after editing through
            # invalid intermediate Jinja. It is a hint, not the authority.
            "symbol": "achievements()",
            "source_content": source,
        },
    )

    current = _document(result["state"], document["id"])
    updated = current["sections"][0]["functions"][0]
    assert updated["id"] == function["id"]
    assert updated["reference_symbol"] == "achievements"
    assert updated["symbol"] == "achievements"
    assert updated["name"] == ""
    assert result["new_symbol"] == "achievements"
    assert all(item["symbol"] != "item" for item in result["state"]["resources"])


def test_whole_construct_update_resolves_single_new_workbench_symbol(tmp_path: Path) -> None:
    _, app = _app(tmp_path)
    document = _private_document(app)
    section = document["sections"][0]
    source = "{% for paragraph in paragraphs %}{{ paragraph }}{% endfor %}"

    result = app.transition_reference(
        1,
        {
            "action": "update",
            "parent_id": document["id"],
            "child_id": section["id"],
            "symbol": source,
            "source_content": source,
        },
    )

    current = _document(result["state"], document["id"])
    updated = current["sections"][0]
    assert updated["id"] == section["id"]
    assert updated["reference_symbol"] == "paragraphs"
    assert updated["name"] == ""
    assert all(item["symbol"] != "paragraph" for item in result["state"]["resources"])


def test_ambiguous_construct_update_is_rejected_without_graph_change(tmp_path: Path) -> None:
    _, app = _app(tmp_path)
    document = _private_document(app)
    section = document["sections"][0]

    with pytest.raises(ValueError, match="multiple new Workbench references"):
        app.transition_reference(
            1,
            {
                "action": "update",
                "parent_id": document["id"],
                "child_id": section["id"],
                "symbol": "not a symbol",
                "source_content": "{{ summary }} {{ experience }}",
            },
        )

    current = _document(app.state(1), document["id"])
    assert current["sections"][0]["id"] == section["id"]
    assert current["sections"][0]["reference_symbol"] == "section"


def test_update_targets_one_duplicate_reference_by_jid_and_range(tmp_path: Path) -> None:
    database, app = _app(tmp_path)
    document = app.create_document(
        1,
        {
            "name": "Duplicate Sections",
            "template_source": "{{ section }}\n{{ section }}",
        },
    )
    repository = database.document_workbench_repository
    edges = repository.list_edges(1, document["id"])
    assert len(edges) == 2
    assert edges[0]["symbol"] == edges[1]["symbol"] == "section"
    assert edges[0]["id"] != edges[1]["id"]
    first_child_id = edges[0]["child_id"]
    second_child_id = edges[1]["child_id"]

    source = "{{ section }}\n{{ experience }}"
    result = app.transition_reference(
        1,
        {
            "action": "update",
            "reference_id": edges[1]["id"],
            "parent_id": document["id"],
            "child_id": second_child_id,
            "symbol": "experience",
            "reference_start": 17,
            "reference_end": 27,
            "source_content": source,
        },
    )

    updated_edges = repository.list_edges(1, document["id"])
    assert updated_edges[0]["id"] == edges[0]["id"]
    assert updated_edges[0]["child_id"] == first_child_id
    assert updated_edges[0]["symbol"] == "section"
    assert updated_edges[1]["id"] == edges[1]["id"]
    assert updated_edges[1]["child_id"] == second_child_id
    assert updated_edges[1]["symbol"] == "experience"

    current = _document(result["state"], document["id"])
    assert [item["id"] for item in current["sections"]] == [first_child_id, second_child_id]
    assert [item["reference_symbol"] for item in current["sections"]] == [
        "section",
        "experience",
    ]
    assert current["sections"][1]["name"] == ""


def test_invalid_update_does_not_change_graph_or_source(tmp_path: Path) -> None:
    _, app = _app(tmp_path)
    document = _private_document(app)
    section = document["sections"][0]

    with pytest.raises(ValueError, match="Jinja syntax error"):
        app.transition_reference(
            1,
            {
                "action": "update",
                "parent_id": document["id"],
                "child_id": section["id"],
                "symbol": "experience",
                "source_content": "{{ experience",
            },
        )

    current = _document(app.state(1), document["id"])
    assert current["template"]["editor_content"] == "{{ section }}"
    assert current["sections"][0]["id"] == section["id"]
    assert current["sections"][0]["reference_symbol"] == "section"
    assert current["sections"][0]["name"] == ""


def test_create_preserves_old_resource_when_it_is_still_referenced(tmp_path: Path) -> None:
    _, app = _app(tmp_path)
    document = _private_document(app)
    section = document["sections"][0]
    app.save(1, {"resource_id": section["id"], "content": "Original body"})

    result = app.transition_reference(
        1,
        {
            "action": "create",
            "parent_id": document["id"],
            "child_id": section["id"],
            "symbol": "experience",
            "source_content": "{{ section }}\n{{ experience }}",
        },
    )

    current = _document(result["state"], document["id"])
    by_symbol = {item["reference_symbol"]: item for item in current["sections"]}
    assert set(by_symbol) == {"section", "experience"}
    assert by_symbol["section"]["id"] == section["id"]
    assert by_symbol["section"]["editor_content"] == "Original body"
    assert by_symbol["experience"]["id"] != section["id"]
    assert result["created_resource_id"] == by_symbol["experience"]["id"]
    assert result["preserve_selected_reference"] is True
    assert result["removed_reference_ids"] == []
    assert result["state"]["orphans"] == []


def test_create_can_stage_replaced_private_resource(tmp_path: Path) -> None:
    _, app = _app(tmp_path)
    document = _private_document(app)
    section = document["sections"][0]
    app.save(1, {"resource_id": section["id"], "content": "Keep me for later"})

    result = app.transition_reference(
        1,
        {
            "action": "create",
            "parent_id": document["id"],
            "child_id": section["id"],
            "symbol": "experience",
            "source_content": "{{ experience }}",
            "disposition": "stage",
        },
    )

    current = _document(result["state"], document["id"])
    assert len(current["sections"]) == 1
    assert current["sections"][0]["reference_symbol"] == "experience"
    assert current["sections"][0]["id"] != section["id"]
    staged = next(item for item in result["state"]["orphans"] if item["id"] == section["id"])
    assert staged["state"] == "orphaned"
    assert staged["editor_content"] == "Keep me for later"
    assert result["staged"] is True


def test_remove_delete_removes_private_resource_tree(tmp_path: Path) -> None:
    database, app = _app(tmp_path)
    document = _private_document(app)
    section = document["sections"][0]
    app.save(1, {"resource_id": section["id"], "content": "{{ helper }}"})
    helper = _document(app.state(1), document["id"])["sections"][0]["functions"][0]
    app.save(1, {"resource_id": helper["id"], "content": "Important helper"})

    result = app.transition_reference(
        1,
        {
            "action": "remove",
            "parent_id": document["id"],
            "child_id": section["id"],
            "source_content": "",
            "disposition": "delete",
        },
    )

    repository = database.document_workbench_repository
    assert repository.get_resource(1, section["id"]) is None
    assert repository.get_resource(1, helper["id"]) is None
    assert section["id"] in result["deleted"]
    assert helper["id"] in result["deleted"]
    assert _document(result["state"], document["id"])["sections"] == []


def test_remove_global_reference_preserves_global_resource(tmp_path: Path) -> None:
    database, app = _app(tmp_path)
    document = _private_document(app)
    section = document["sections"][0]
    app.update_resource(1, {"resource_id": section["id"], "visibility": "global"})

    result = app.transition_reference(
        1,
        {
            "action": "remove",
            "parent_id": document["id"],
            "child_id": section["id"],
            "source_content": "",
            "disposition": "remove",
        },
    )

    preserved = database.document_workbench_repository.require_resource(1, section["id"])
    assert preserved["visibility"] == "global"
    assert preserved["state"] == "active"
    assert _document(result["state"], document["id"])["sections"] == []
    assert any(item["id"] == section["id"] for item in result["state"]["global_sections"])


def test_preview_validation_keeps_private_template_unchanged(tmp_path: Path) -> None:
    _, app = _app(tmp_path)
    document = app.create_document(1, {"name": "Resume"})
    template_id = document["template_id"]
    section = document["sections"][0]

    result = app.transition_reference(
        1,
        {
            "action": "update",
            "parent_id": document["id"],
            "child_id": section["id"],
            "symbol": "experience",
            "source_content": document["template"]["content"].replace(
                "{{ section }}", "{{ experience }}"
            ),
            "disposition": "preview",
        },
    )

    assert result["validated"] is True
    current = _document(app.state(1), document["id"])
    assert current["template_id"] == template_id
    assert current["template"]["visibility"] == "private"
    assert current["template"]["owner_id"] == document["id"]
    assert "system_template" not in current["template"]["settings"]
    assert current["sections"][0]["id"] == section["id"]
    assert current["sections"][0]["reference_symbol"] == "section"


def test_invalid_update_keeps_private_template_unchanged(tmp_path: Path) -> None:
    _, app = _app(tmp_path)
    document = app.create_document(1, {"name": "Resume"})
    template_id = document["template_id"]
    section = document["sections"][0]

    with pytest.raises(ValueError, match="Jinja syntax error"):
        app.transition_reference(
            1,
            {
                "action": "update",
                "parent_id": document["id"],
                "child_id": section["id"],
                "symbol": "experience",
                "source_content": "{{ experience",
            },
        )

    current = _document(app.state(1), document["id"])
    assert current["template_id"] == template_id
    assert current["template"]["visibility"] == "private"
    assert current["template"]["owner_id"] == document["id"]
    assert "system_template" not in current["template"]["settings"]
