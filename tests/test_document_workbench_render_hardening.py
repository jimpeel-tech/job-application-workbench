from __future__ import annotations

from pathlib import Path

import pytest

from jaw.application.document_workbench_render import (
    DocumentWorkbenchRenderer,
    WorkbenchRenderError,
)
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase
from jaw.documents.contracts import DocumentRenderResult


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {
            "user": {"first_name": "Jane", "last_name": "Engineer"},
            "work_history": [],
        }


class _Renderer:
    name = "tectonic"
    available = True

    def render(self, request):
        return DocumentRenderResult(
            pdf_bytes=b"%PDF-hardening",
            rendered_source=request.template_source,
            diagnostics=(),
            renderer=self.name,
            command=("fake",),
            duration_ms=1,
        )


def _workspace(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    document = service.create_document(1, {"name": "Resume"})
    renderer = DocumentWorkbenchRenderer(
        database.document_workbench_repository,
        renderer=_Renderer(),
    )
    return renderer, document


def _context(**overrides):
    value = {
        "user": {"first_name": "Jane", "last_name": "Engineer"},
        "job_ref": {},
        "work_exp": [],
        "cap": {},
        "system": {},
    }
    value.update(overrides)
    return value


def test_runtime_boundary_normalizes_work_experience_highlights(tmp_path: Path):
    renderer, _ = _workspace(tmp_path)

    runtime = renderer._runtime_context(
        _context(
            work_exp=[
                {
                    "company": "Example Corp",
                    "highlights": "• Built platform\r\n- Reduced toil",
                }
            ]
        )
    )

    assert runtime["work_exp"][0]["highlights"] == [
        "Built platform",
        "Reduced toil",
    ]


def test_output_filename_missing_value_fails_with_workbench_error(tmp_path: Path):
    renderer, _ = _workspace(tmp_path)

    with pytest.raises(WorkbenchRenderError, match="Could not render output filename"):
        renderer._render_text("{{ missing }}.pdf", _context(), label="output filename")


def test_output_directory_failure_preserves_preview(monkeypatch, tmp_path: Path):
    renderer, document = _workspace(tmp_path)
    blocked = tmp_path / "blocked"
    original_mkdir = Path.mkdir

    def fail_blocked_directory(self, *args, **kwargs):
        if self == blocked:
            raise OSError("permission denied")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_blocked_directory)

    result = renderer.generate(
        1,
        document["id"],
        _context(),
        output_directory=blocked,
    )

    assert result["pdf_base64"]
    assert result["output_written"] is False
    assert "output directory could not be prepared" in result["warning"]
    assert "permission denied" in result["warning"]


def test_output_file_failure_preserves_preview(monkeypatch, tmp_path: Path):
    renderer, document = _workspace(tmp_path)
    output_directory = tmp_path / "downloads"
    original_write_bytes = Path.write_bytes

    def fail_pdf_write(self, data):
        if self.parent == output_directory and self.suffix.casefold() == ".pdf":
            raise OSError("file is locked")
        return original_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", fail_pdf_write)

    result = renderer.generate(
        1,
        document["id"],
        _context(),
        output_directory=output_directory,
    )

    assert result["pdf_base64"]
    assert result["output_written"] is False
    assert "could not be replaced" in result["warning"]
    assert "Close the file" in result["warning"]
