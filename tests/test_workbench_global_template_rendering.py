from __future__ import annotations

from pathlib import Path

from jaw.application.document_workbench_application import DocumentWorkbenchApplication
from jaw.application.document_workbench_render import DocumentWorkbenchRenderer
from jaw.database import JobDatabase
from jaw.documents.contracts import DocumentRenderResult
from jaw.documents.workbench_symbols import reference_jinja_symbol


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {
            "active_user_id": user_id or 1,
            "user": {"first_name": "Jane", "last_name": "Engineer"},
        }


class _Renderer:
    name = "tectonic"
    available = True

    def __init__(self) -> None:
        self.requests = []

    def render(self, request):
        self.requests.append(request)
        return DocumentRenderResult(
            pdf_bytes=b"%PDF-shared-template",
            rendered_source=request.template_source,
            diagnostics=(),
            renderer=self.name,
            command=("fake",),
            duration_ms=1,
        )


def _document(state: dict, document_id: str) -> dict:
    return next(item for item in state["documents"] if item["id"] == document_id)


def test_shared_global_template_renders_each_documents_own_section_graph(
    tmp_path: Path,
) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    app = DocumentWorkbenchApplication(database, _UserData())
    repository = database.document_workbench_repository

    first = app.create_document(
        1,
        {"name": "First", "template_source": "{{ body }}"},
    )
    second = app.create_document(
        1,
        {"name": "Second", "template_source": "{{ body }}"},
    )
    shared_template_id = first["template_id"]
    app.update_resource(
        1,
        {"resource_id": shared_template_id, "visibility": "global"},
    )
    shared_state = app.update_resource(
        1,
        {"resource_id": second["id"], "template_id": shared_template_id},
    )["state"]

    first_state = _document(shared_state, first["id"])
    second_state = _document(shared_state, second["id"])
    first_section = first_state["sections"][0]
    second_section = second_state["sections"][0]
    assert first_section["id"] != second_section["id"]
    assert first_section["reference_id"] != second_section["reference_id"]

    app.save(1, {"resource_id": first_section["id"], "content": "First body"})
    app.save(1, {"resource_id": second_section["id"], "content": "Second body"})

    fake = _Renderer()
    renderer = DocumentWorkbenchRenderer(repository, renderer=fake)
    context = {
        "user": {},
        "job": {},
        "work_history": [],
        "capabilities": {},
        "system": {},
    }

    renderer.generate(1, first["id"], context, output_directory=tmp_path)
    renderer.generate(1, second["id"], context, output_directory=tmp_path)

    assert len(fake.requests) == 2
    first_edge = repository.list_edges(1, first["id"])[0]
    second_edge = repository.list_edges(1, second["id"])[0]
    first_key = reference_jinja_symbol(first_edge["id"])
    second_key = reference_jinja_symbol(second_edge["id"])
    assert first_key != second_key

    first_request, second_request = fake.requests
    assert first_request.template_source == f"{{{{ {first_key} }}}}"
    assert second_request.template_source == f"{{{{ {second_key} }}}}"
    assert first_request.context[first_key].content == "First body"
    assert second_request.context[second_key].content == "Second body"
    assert second_key not in first_request.context
    assert first_key not in second_request.context
