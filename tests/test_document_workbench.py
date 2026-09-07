from __future__ import annotations

from pathlib import Path

import pytest

from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase
from jaw.documents.workbench_symbols import referenced_symbols


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {
            "user": {
                "first_name": "Jane",
                "last_name": "Engineer",
                "email": "jane@example.com",
            }
        }


def _service(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    return database, service


def test_new_documents_get_independent_private_templates_and_sections(tmp_path: Path) -> None:
    _, service = _service(tmp_path)

    first = service.create_document(1, {"name": "Cover Letter"})
    second = service.create_document(1, {"name": "Resume"})

    assert first["template_id"] != second["template_id"]
    assert first["template"]["name"] == "Cover Letter"
    assert second["template"]["name"] == "Resume"
    assert first["template"]["visibility"] == "private"
    assert second["template"]["visibility"] == "private"
    assert first["template"]["owner_id"] == first["id"]
    assert second["template"]["owner_id"] == second["id"]
    assert first["template"]["settings"] == {
        "renderer": "tectonic",
        "format": "latex_jinja",
    }
    assert first["template"]["content"].count("{{ section }}") == 1
    assert len(first["sections"]) == 1
    assert len(second["sections"]) == 1
    assert first["sections"][0]["id"] != second["sections"][0]["id"]
    section = first["sections"][0]
    assert section["reference_symbol"] == "section"
    assert section["name"] == ""
    assert section["visibility"] == "private"
    assert section["owner_id"] == first["id"]
    assert section["settings"]["content_shape"] == "paragraphs"


def test_template_checkpoint_keeps_same_template_jid_and_discovers_new_sections(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    document = service.create_document(1, {"name": "Resume"})
    template = document["template"]
    source = template["content"].replace(
        "{{ section }}",
        "{{ section }}\n{{ intro }}\n{{ intro_2 }}",
    )

    result = service.checkpoint(
        1,
        {
            "resource_id": template["id"],
            "document_id": document["id"],
            "content": source,
            "cursor_start": 14,
            "cursor_end": 14,
        },
    )

    assert "template_replaced" not in result
    assert len(result["changes"]["created"]) == 2
    updated = next(item for item in result["state"]["documents"] if item["id"] == document["id"])
    assert updated["template_id"] == template["id"]
    assert [item["reference_symbol"] for item in updated["sections"]] == [
        "section",
        "intro",
        "intro_2",
    ]
    assert updated["template"]["dirty"] is True
    assert updated["template"]["visibility"] == "private"

    restarted = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    restored = restarted.state(1)
    restored_doc = next(item for item in restored["documents"] if item["id"] == document["id"])
    assert restored_doc["template_id"] == template["id"]
    assert restored_doc["template"]["dirty"] is True
    assert restored_doc["template"]["editor_content"] == source


def test_ctrl_save_clears_recovery_buffer_and_keeps_template_jid(tmp_path: Path) -> None:
    _, service = _service(tmp_path)
    document = service.create_document(1, {"name": "Resume"})
    template = document["template"]
    source = template["content"].replace(
        "{{ section }}",
        "{{ section }}\n{{ experience }}",
    )
    checkpoint = service.checkpoint(
        1,
        {
            "resource_id": template["id"],
            "document_id": document["id"],
            "content": source,
        },
    )
    assert "template_replaced" not in checkpoint

    saved = service.save(
        1,
        {
            "resource_id": template["id"],
            "document_id": document["id"],
            "content": source,
        },
    )

    assert saved["resource"]["id"] == template["id"]
    assert saved["resource"]["content"] == source
    final_doc = next(item for item in saved["state"]["documents"] if item["id"] == document["id"])
    assert final_doc["template_id"] == template["id"]
    assert final_doc["template"]["dirty"] is False
    assert [item["reference_symbol"] for item in final_doc["sections"]] == [
        "section",
        "experience",
    ]


def test_template_loop_creates_paragraphs_section_but_not_loop_local(tmp_path: Path) -> None:
    _, service = _service(tmp_path)
    source = r"""% Content sections supplied by JAW
{% for paragraph in paragraphs %}

\CoverParagraph{
  {{ paragraph }}
}

{% endfor %}
"""
    document = service.create_document(
        1,
        {"name": "Cover Letter", "template_source": source},
    )

    assert [section["reference_symbol"] for section in document["sections"]] == ["paragraphs"]
    assert all(resource["symbol"] != "paragraph" for resource in service.state(1)["resources"])


def test_generation_variables_are_locals_not_function_resources(tmp_path: Path) -> None:
    _, service = _service(tmp_path)
    document = service.create_document(1, {"name": "Cover Letter"})
    section = document["sections"][0]
    source = """<paragraphs:list>
Write three paragraphs using {{ job_ref.title }}.
</>
{% for paragraph in paragraphs %}{{ paragraph }}{% endfor %}"""

    result = service.checkpoint(1, {"resource_id": section["id"], "content": source})

    assert result["changes"]["created"] == []
    current = next(item for item in result["state"]["documents"] if item["id"] == document["id"])
    assert current["sections"][0]["functions"] == []
    assert referenced_symbols(source) == []


def test_template_rejects_generation_blocks(tmp_path: Path) -> None:
    _, service = _service(tmp_path)
    document = service.create_document(1, {"name": "Cover Letter"})

    with pytest.raises(ValueError, match="Generation blocks belong in Sections or Functions"):
        service.checkpoint(
            1,
            {
                "resource_id": document["template_id"],
                "document_id": document["id"],
                "content": "<paragraphs:list>Write paragraphs</>",
            },
        )


def test_checkpoint_never_detaches_existing_resource_without_explicit_transition(
    tmp_path: Path,
) -> None:
    _, service = _service(tmp_path)
    document = service.create_document(1, {"name": "Cover Letter"})
    template = document["template"]
    section = document["sections"][0]
    service.save(1, {"resource_id": section["id"], "content": "Keep this text."})

    result = service.checkpoint(
        1,
        {
            "resource_id": template["id"],
            "document_id": document["id"],
            "content": template["content"].replace("{{ section }}", ""),
        },
    )

    assert result["changes"] == {"created": [], "orphaned": [], "deleted": []}
    current = next(item for item in result["state"]["documents"] if item["id"] == document["id"])
    assert current["sections"][0]["id"] == section["id"]
    assert current["sections"][0]["reference_symbol"] == "section"
    assert result["state"]["orphans"] == []


def test_staged_resource_is_not_garbage_collected_when_content_is_cleared(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    document = service.create_document(1, {"name": "Cover Letter"})
    section = document["sections"][0]
    repository = database.document_workbench_repository

    repository.unlink(1, document["id"], section["id"])
    repository.update_resource(1, section["id"], state="orphaned")
    service.save(1, {"resource_id": section["id"], "content": ""})

    preserved = repository.require_resource(1, section["id"])
    assert preserved["state"] == "orphaned"
    assert any(item["id"] == section["id"] for item in service.state(1)["orphans"])


def test_dragging_staged_resource_reuses_same_jid_and_makes_it_private_again(
    tmp_path: Path,
) -> None:
    database, service = _service(tmp_path)
    source_doc = service.create_document(1, {"name": "Source"})
    section = source_doc["sections"][0]
    service.save(1, {"resource_id": section["id"], "content": "Reusable draft"})
    repository = database.document_workbench_repository
    repository.unlink(1, source_doc["id"], section["id"])
    repository.update_resource(1, section["id"], state="orphaned")
    target = service.create_document(1, {"name": "Target"})

    linked = service.link_existing(1, {"parent_id": target["id"], "child_id": section["id"]})

    moved = next(item for item in linked["state"]["resources"] if item["id"] == section["id"])
    assert moved["id"] == section["id"]
    assert moved["state"] == "active"
    assert moved["visibility"] == "private"
    assert moved["owner_id"] == target["id"]


def test_global_resources_allow_duplicate_reference_symbols(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    document = service.create_document(1, {"name": "Cover Letter"})
    repository = database.document_workbench_repository
    first = repository.create_resource(
        1,
        "section",
        symbol="intro",
        visibility="global",
        content="First",
        settings={"content_shape": "paragraphs"},
    )
    second = repository.create_resource(
        1,
        "section",
        symbol="intro",
        visibility="global",
        content="Second",
        settings={"content_shape": "paragraphs"},
    )

    one = service.link_existing(1, {"parent_id": document["id"], "child_id": first["id"]})
    two = service.link_existing(1, {"parent_id": document["id"], "child_id": second["id"]})

    assert one["symbol"] == two["symbol"] == "intro"
    assert one["reference_id"] != two["reference_id"]
    assert first["name"] == second["name"] == ""


def test_jinja_locals_jaw_roots_and_latex_raw_are_not_resources() -> None:
    source = r"""
{% for item in work_exp %}
{{ item.company }}
{{ user.full_name }}
{{ job_ref.title }}
{{ cap.sets }}
{{ system.current_date }}
{{ latex_raw(user.signature_latex) }}
{{ dump(job_ref) }}
{{ describe(work_exp) }}
{{ private_summary }}
{% endfor %}
"""

    assert referenced_symbols(source) == ["private_summary"]


def test_jaw_palette_exposes_dynamic_system_values_and_raw_latex_helper(tmp_path: Path) -> None:
    _, service = _service(tmp_path)

    state = service.state(1)
    system = state["generation_context"]["system"]
    palette_system = state["jaw_objects"]["system"]
    entries = {item["name"] for item in state["jaw_objects"]["methods"]}

    assert system["current_date"]
    assert system["current_year"]
    assert palette_system["current_date"] == system["current_date"]
    assert palette_system["current_year"] == system["current_year"]
    assert "system.current_date" not in entries
    assert "system.current_year" not in entries
    assert "latex_raw(...)" in entries
