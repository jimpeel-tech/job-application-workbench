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


def test_update_uses_final_unique_reference_when_editor_hint_is_stale(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    app = DocumentWorkbenchApplication(database, _UserData())
    repository = database.document_workbench_repository

    document = app.create_document(1, {"name": "Transition Hints"})
    section = document["sections"][0]
    saved = app.save(
        1,
        {
            "resource_id": section["id"],
            "content": "{{ accomplishments() }}",
        },
    )
    current = next(
        item for item in saved["state"]["documents"] if item["id"] == document["id"]
    )
    function = current["sections"][0]["functions"][0]
    original_reference_id = function["reference_id"]
    original_resource_id = function["id"]

    source = "{% for item in achievements() %}\n{{ item }}\n{% endfor %}"
    result = app.transition_reference(
        1,
        {
            "action": "update",
            "reference_id": original_reference_id,
            "parent_id": section["id"],
            "child_id": original_resource_id,
            # Simulate browser tracking after editing through invalid Jinja: both
            # the token text and tracked range are stale, but final source has one
            # unambiguous Workbench reference.
            "symbol": "accomplish",
            "reference_start": 0,
            "reference_end": 2,
            "source_content": source,
        },
    )

    assert result["reference_id"] == original_reference_id
    assert result["resource_id"] == original_resource_id
    assert result["new_symbol"] == "achievements"

    edge = repository.require_reference(1, original_reference_id)
    function_resource = repository.require_resource(1, original_resource_id)
    assert edge["child_id"] == original_resource_id
    assert edge["symbol"] == "achievements"
    assert function_resource["symbol"] == "achievements"
    assert repository.get_buffer(1, section["id"])["content"] == source
