from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jaw.documents import (
    DocumentRenderError,
    DocumentRenderRequest,
    TectonicRenderer,
    escape_latex,
    find_tectonic,
    render_latex_template,
)
from jaw.documents import tectonic as tectonic_module


def _cover_letter_context() -> dict[str, object]:
    return {
        "candidate_name": "Jamie Example",
        "position_name": "Platform & Reliability Engineer",
        "date": "August 16, 2026",
        "greeting": "Dear Hiring Team,",
        "phone": "+1 (555) 010-2000",
        "email": "jamie@example.test",
        "linkedin": "linkedin.com/in/jamie-example",
        "website": "example.test",
        "paragraphs": [
            {
                "content": "I improve reliability by 50% across R&D systems.",
                "enabled": True,
            },
            {"content": "This paragraph is disabled.", "enabled": False},
        ],
    }


def test_escape_latex_makes_tex_metacharacters_inert():
    assert escape_latex(None) == ""
    assert escape_latex("\\{}$&#%_~^") == (
        r"\textbackslash{}\{\}\$\&\#\%\_\textasciitilde{}"
        r"\textasciicircum{}"
    )
    assert escape_latex("line 1\r\nline 2") == "line 1\nline 2"


def test_render_latex_template_is_strict_and_uses_latex_filter():
    assert render_latex_template(
        r"Hello {{ name | latex }}",
        {"name": "R&D_1"},
    ) == r"Hello R\&D\_1"

    with pytest.raises(DocumentRenderError, match="missing") as failure:
        render_latex_template("{{ missing }}", {})
    assert failure.value.diagnostics[0].source == "jinja2"


def test_autoescape_text_escapes_expression_results_and_supports_raw_latex():
    rendered = render_latex_template(
        r"{{ name | upper }}|{{ latex_raw(markup) }}",
        {"name": "R&D_1", "markup": r"\textbf{Ready & willing}"},
        autoescape_text=True,
    )

    assert rendered == r"R\&D\_1|\textbf{Ready & willing}"


def test_latex_filter_remains_idempotent_inside_autoescape_boundary():
    rendered = render_latex_template(
        r"{{ name | latex }}",
        {"name": "R&D_1"},
        autoescape_text=True,
    )

    assert rendered == r"R\&D\_1"


def test_find_tectonic_prefers_configured_executable(tmp_path: Path):
    configured = tmp_path / "tectonic.exe"
    configured.write_bytes(b"executable")

    assert find_tectonic(configured) == configured.resolve()


def test_find_tectonic_search_path_prefers_configured_directory(tmp_path: Path):
    configured = tmp_path / "fonts"
    configured.mkdir()

    assert tectonic_module.find_tectonic_search_path(configured) == configured.resolve()


def test_find_tectonic_search_path_defaults_to_packaged_font_resource_directory():
    expected = Path(tectonic_module.__file__).resolve().parent.parent / "resources" / "fonts"

    assert tectonic_module.find_tectonic_search_path() == expected.resolve()
    assert (expected / "README.md").is_file()
    assert not any(
        item.suffix.lower() in {".ttf", ".otf", ".ttc"}
        for item in expected.iterdir()
        if item.is_file()
    )


def test_tectonic_renderer_invokes_untrusted_mode_and_returns_pdf(
    monkeypatch,
    tmp_path: Path,
):
    executable = tmp_path / "tectonic.exe"
    executable.write_bytes(b"executable")
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "OpenSans-Regular.ttf").write_bytes(b"font-data")
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        working_directory = Path(kwargs["cwd"])
        observed["staged_font"] = (
            working_directory / "OpenSans-Regular.ttf"
        ).read_bytes()
        output_directory = Path(command[command.index("--outdir") + 1])
        source_path = Path(command[-1])
        (output_directory / f"{source_path.stem}.pdf").write_bytes(b"%PDF-fake")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="processing complete",
            stderr="warning: fallback font used",
        )

    monkeypatch.setattr(tectonic_module.subprocess, "run", fake_run)
    renderer = TectonicRenderer(executable, search_path=fonts, timeout=42)
    request = DocumentRenderRequest(
        "Hello {{ name | latex }}",
        {"name": "R&D"},
        output_name="My Document",
        only_cached=True,
    )

    result = renderer.render(request)

    command = observed["command"]
    kwargs = observed["kwargs"]
    assert result.pdf_bytes == b"%PDF-fake"
    assert result.rendered_source == r"Hello R\&D"
    assert result.renderer == "tectonic"
    assert result.duration_ms >= 0
    assert "--untrusted" in command
    assert "--only-cached" in command
    assert "-Z" not in command
    assert observed["staged_font"] == b"font-data"
    assert command[-1].endswith("My-Document.tex")
    assert kwargs["env"]["TECTONIC_UNTRUSTED_MODE"] == "1"
    assert kwargs["timeout"] == 42
    assert {item.source for item in result.diagnostics} == {
        "tectonic.stdout",
        "tectonic.stderr",
    }


def test_tectonic_renderer_exposes_source_and_diagnostics_on_failure(
    monkeypatch,
    tmp_path: Path,
):
    executable = tmp_path / "tectonic.exe"
    executable.write_bytes(b"executable")

    monkeypatch.setattr(
        tectonic_module.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="error: missing package",
        ),
    )

    with pytest.raises(DocumentRenderError, match="could not render") as failure:
        TectonicRenderer(executable).render(
            DocumentRenderRequest("Hello {{ name }}", {"name": "Jamie"})
        )

    assert failure.value.rendered_source == "Hello Jamie"
    assert failure.value.diagnostics[0].level == "error"
    assert "missing package" in failure.value.diagnostics[0].message


def test_tectonic_renderer_reports_missing_executable(monkeypatch):
    monkeypatch.setattr(tectonic_module, "find_tectonic", lambda configured=None: None)

    with pytest.raises(DocumentRenderError, match="Tectonic was not found"):
        TectonicRenderer().render(DocumentRenderRequest("Hello", {}))
