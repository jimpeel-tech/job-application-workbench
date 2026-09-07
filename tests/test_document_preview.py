from pathlib import Path

from jaw.application.document_workbench_render import DocumentWorkbenchRenderer
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase
from jaw.documents.contracts import DocumentRenderResult
from jaw.documents.workbench_symbols import reference_jinja_symbol


class _UserData:
    def read(self, *, user_id=None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


class _Renderer:
    name = "tectonic"
    available = True

    def __init__(self) -> None:
        self.requests = []

    def render(self, request):
        self.requests.append(request)
        return DocumentRenderResult(
            pdf_bytes=b"%PDF-preview",
            rendered_source=request.template_source,
            diagnostics=(),
            renderer=self.name,
            command=("fake",),
            duration_ms=7,
        )


def test_preview_renders_immediate_working_buffers_without_writing_output(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(1, {"name": "Preview Test"})
    section = document["sections"][0]

    # Simulate a recovery checkpoint that is older than the textarea content.
    service.checkpoint(
        1,
        {"resource_id": section["id"], "content": "Older checkpoint content"},
    )

    fake = _Renderer()
    result = DocumentWorkbenchRenderer(
        repository,
        renderer=fake,
        working_buffers={section["id"]: "Immediate editor content"},
    ).generate(
        1,
        document["id"],
        {
            "user": {"first_name": "Jane", "last_name": "Engineer"},
            "job_ref": {},
            "work_exp": [],
            "cap": {},
            "system": {},
        },
        # Preview must not resolve, create, or write an output directory.
        output_directory="relative/path/that/would-be-invalid-for-generate",
        write_output=False,
    )

    edge = repository.list_edges(1, document["id"])[0]
    section_value = fake.requests[0].context[reference_jinja_symbol(edge["id"])]
    assert section_value.content == "Immediate editor content"
    assert result["pdf_base64"]
    assert result["output_written"] is False
    assert result["output_path"] == ""
    assert result["output_directory"] == ""
    assert not (tmp_path / "relative").exists()
