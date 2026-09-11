from __future__ import annotations

from datetime import date
from pathlib import Path

from jaw.application.document_workbench_render import DocumentWorkbenchRenderer
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase
from jaw.documents import render_latex_template
from jaw.documents.contracts import DocumentRenderResult
from jaw.documents.text_generation import StructuredTextGenerationResult
from jaw.documents.workbench_symbols import reference_jinja_symbol


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {
            "user": {"first_name": "Jane", "last_name": "Engineer"},
            "work_history": [
                {"company": "Example Corp", "title": "Platform Engineer", "enabled": True}
            ],
        }


class _Renderer:
    name = "tectonic"
    available = True

    def __init__(self) -> None:
        self.requests = []

    def render(self, request):
        self.requests.append(request)
        rendered = request.template_source
        for key, value in request.context.items():
            rendered = rendered.replace("{{ " + key + " }}", str(value))
        return DocumentRenderResult(
            pdf_bytes=b"%PDF-workbench",
            rendered_source=rendered,
            diagnostics=(),
            renderer=self.name,
            command=("fake",),
            duration_ms=12,
        )


class _TextGenerator:
    def __init__(self) -> None:
        self.requests = []

    def generate_structured(self, request):
        self.requests.append(request)
        value = (
            ["Built a reliable platform", "Reduced operational toil"]
            if request.output_type == "list"
            else "Generated text"
        )
        return StructuredTextGenerationResult(
            value=value,
            provider=request.provider,
            model=request.model,
        )


def _workspace(tmp_path: Path):
    database = JobDatabase(tmp_path / "jaw.db")
    service = DocumentWorkbenchService(database.document_workbench_repository, _UserData())
    document = service.create_document(1, {"name": "Resume"})
    return database, service, document


def _section_request_value(repository, document_id: str, request, index: int = 0):
    edge = repository.list_edges(1, document_id)[index]
    return request.context[reference_jinja_symbol(edge["id"])]


def _context(**overrides):
    value = {
        "user": {},
        "job_ref": {},
        "work_exp": [],
        "cap": {},
        "system": {},
    }
    value.update(overrides)
    return value


def test_renderer_uses_dirty_buffers_without_saving_them(tmp_path: Path) -> None:
    database, service, document = _workspace(tmp_path)
    repository = database.document_workbench_repository
    section = document["sections"][0]
    service.checkpoint(1, {"resource_id": section["id"], "content": "Unsaved preview text"})
    fake = _Renderer()
    renderer = DocumentWorkbenchRenderer(repository, renderer=fake)
    output_directory = tmp_path / "downloads"

    result = renderer.generate(
        1,
        document["id"],
        _context(user={"first_name": "Jane", "last_name": "Engineer"}),
        output_directory=output_directory,
    )

    assert result["pdf_base64"]
    assert result["output_written"] is True
    assert Path(result["output_path"]).parent == output_directory.resolve()
    assert result["output_directory"] == str(output_directory.resolve())
    assert _section_request_value(repository, document["id"], fake.requests[0]).content == (
        "Unsaved preview text"
    )
    assert fake.requests[0].autoescape_text is True
    stored = repository.require_resource(1, section["id"])
    assert stored["content"] == ""
    assert repository.get_buffer(1, section["id"]) is not None


def test_renderer_keeps_duplicate_visible_section_symbols_independent(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(
        1,
        {
            "name": "Duplicate Sections",
            "template_source": "{{ section }}|{{ section }}",
        },
    )
    assert [item["reference_symbol"] for item in document["sections"]] == [
        "section",
        "section",
    ]
    assert document["sections"][0]["id"] != document["sections"][1]["id"]

    service.save(1, {"resource_id": document["sections"][0]["id"], "content": "First"})
    service.save(1, {"resource_id": document["sections"][1]["id"], "content": "Second"})

    fake = _Renderer()
    DocumentWorkbenchRenderer(repository, renderer=fake).generate(
        1,
        document["id"],
        _context(),
        output_directory=tmp_path,
    )

    edges = repository.list_edges(1, document["id"])
    first_key = reference_jinja_symbol(edges[0]["id"])
    second_key = reference_jinja_symbol(edges[1]["id"])
    request = fake.requests[0]
    assert first_key != second_key
    assert request.template_source == f"{{{{ {first_key} }}}}|{{{{ {second_key} }}}}"
    assert request.context[first_key].content == "First"
    assert request.context[second_key].content == "Second"


def test_output_directory_accepts_downloads_and_rejects_relative_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert DocumentWorkbenchRenderer._output_directory(None) == tmp_path / "Downloads"
    assert DocumentWorkbenchRenderer._output_directory("Downloads") == tmp_path / "Downloads"

    try:
        DocumentWorkbenchRenderer._output_directory("relative/output")
    except ValueError as error:
        assert "absolute path" in str(error)
    else:
        raise AssertionError("relative output directory should be rejected")


def test_list_and_paragraph_sections_are_iterable(tmp_path: Path) -> None:
    database, service, document = _workspace(tmp_path)
    repository = database.document_workbench_repository
    section = document["sections"][0]
    renderer = DocumentWorkbenchRenderer(repository, renderer=_Renderer())
    runtime = renderer._runtime_context(_context())

    service.save(1, {"resource_id": section["id"], "content": "- Kubernetes\n- Terraform"})
    repository.update_resource(1, section["id"], settings={"content_shape": "list"})
    list_value = renderer._section_value(
        1,
        repository.require_resource(1, section["id"]),
        runtime,
        provider="ollama",
        model="qwen3:14b",
        generation_log=[],
    )
    assert list(list_value) == ["Kubernetes", "Terraform"]

    service.save(
        1,
        {"resource_id": section["id"], "content": "First paragraph.\n\n\nSecond paragraph."},
    )
    repository.update_resource(1, section["id"], settings={"content_shape": "paragraphs"})
    paragraph_value = renderer._section_value(
        1,
        repository.require_resource(1, section["id"]),
        runtime,
        provider="ollama",
        model="qwen3:14b",
        generation_log=[],
    )
    assert list(paragraph_value) == ["First paragraph.", "", "Second paragraph."]


def test_section_text_stays_raw_until_latex_template_boundary(tmp_path: Path) -> None:
    database, service, document = _workspace(tmp_path)
    repository = database.document_workbench_repository
    section = document["sections"][0]
    renderer = DocumentWorkbenchRenderer(repository, renderer=_Renderer())
    runtime = renderer._runtime_context(_context())

    service.save(1, {"resource_id": section["id"], "content": "R&D improved by 50% with foo_bar #1"})
    value = renderer._section_value(
        1,
        repository.require_resource(1, section["id"]),
        runtime,
        provider="ollama",
        model="qwen3:14b",
        generation_log=[],
    )

    assert str(value) == "R&D improved by 50% with foo_bar #1"
    assert render_latex_template(
        "{{ section }}",
        {"section": value},
        autoescape_text=True,
    ) == r"R\&D improved by 50\% with foo\_bar \#1"


def test_runtime_exposes_derived_full_name_system_and_work_exp(tmp_path: Path) -> None:
    database, _, _ = _workspace(tmp_path)
    renderer = DocumentWorkbenchRenderer(database.document_workbench_repository, renderer=_Renderer())

    runtime = renderer._runtime_context(
        _context(
            user={"first_name": "Jane", "last_name": "Engineer"},
            work_exp=[{"company": "Example Corp", "title": "Engineer"}],
            system={"current_date": "stale", "current_year": "1900"},
        )
    )

    today = date.today()
    assert runtime["user"]["full_name"] == "Jane Engineer"
    assert runtime["system"]["current_date"] == today.strftime("%B %d, %Y").replace(" 0", " ")
    assert runtime["system"]["current_year"] == str(today.year)
    assert runtime["work_exp"] == [
        {"company": "Example Corp", "title": "Engineer", "highlights": []}
    ]
    assert runtime["csv"](["AWS", "OCI"]) == "AWS, OCI"


def test_section_executes_generation_blocks_directly(tmp_path: Path) -> None:
    database, service, document = _workspace(tmp_path)
    repository = database.document_workbench_repository
    section = document["sections"][0]
    service.save(
        1,
        {
            "resource_id": section["id"],
            "content": """<bullets:list>
Generate two bullets using {{ work_exp }}.
</>
{% for bullet in bullets %}- {{ bullet }}\n{% endfor %}""",
        },
    )
    repository.update_resource(1, section["id"], settings={"content_shape": "list"})

    pdf_renderer = _Renderer()
    text_generator = _TextGenerator()
    result = DocumentWorkbenchRenderer(
        repository,
        renderer=pdf_renderer,
        text_generator=text_generator,
    ).generate(
        1,
        document["id"],
        _context(
            user={"first_name": "Jane", "last_name": "Engineer"},
            job_ref={"title": "Staff SRE"},
            work_exp=[{"company": "Example Corp", "title": "Engineer"}],
        ),
        output_directory=tmp_path,
        analysis_settings={"provider": "ollama", "model": "qwen3:14b"},
    )

    assert len(text_generator.requests) == 1
    assert text_generator.requests[0].context == {
        "work_exp": [
            {"company": "Example Corp", "title": "Engineer", "highlights": []}
        ]
    }
    section_value = _section_request_value(repository, document["id"], pdf_renderer.requests[0])
    assert "Built a reliable platform" in section_value.content
    assert result["generations"][0]["resource_kind"] == "section"
    assert result["generations"][0]["resource"] == section["symbol"]


def test_renderer_executes_function_helpers_with_inherited_provider(tmp_path: Path) -> None:
    database, service, document = _workspace(tmp_path)
    repository = database.document_workbench_repository
    section = document["sections"][0]

    service.save(1, {"resource_id": section["id"], "content": "{{ resume_bullets() }}"})
    state = service.state(1)
    current = next(item for item in state["documents"] if item["id"] == document["id"])
    function = current["sections"][0]["functions"][0]
    service.save(
        1,
        {
            "resource_id": function["id"],
            "content": """{% set jobs = work_exp %}
<bullets:list>
Generate two resume bullets from {{ jobs }}.
</>
{% for bullet in bullets %}- {{ bullet }}\n{% endfor %}""",
        },
    )

    pdf_renderer = _Renderer()
    text_generator = _TextGenerator()
    result = DocumentWorkbenchRenderer(
        repository,
        renderer=pdf_renderer,
        text_generator=text_generator,
    ).generate(
        1,
        document["id"],
        _context(
            user={"first_name": "Jane", "last_name": "Engineer"},
            job_ref={"title": "Staff SRE"},
            work_exp=[{"company": "Example Corp", "title": "Engineer"}],
        ),
        output_directory=tmp_path,
        analysis_settings={"provider": "ollama", "model": "qwen3:14b"},
    )

    assert text_generator.requests[0].provider == "ollama"
    assert text_generator.requests[0].model == "qwen3:14b"
    assert text_generator.requests[0].context == {
        "jobs": [
            {"company": "Example Corp", "title": "Engineer", "highlights": []}
        ]
    }
    section_value = _section_request_value(repository, document["id"], pdf_renderer.requests[0])
    assert "Built a reliable platform" in section_value.content
    assert result["generations"][0]["resource_kind"] == "function"
    assert result["generations"][0]["resource"] == "resume_bullets"


def test_renderer_exposes_function_helpers_as_values_without_call_syntax(tmp_path: Path) -> None:
    database, service, document = _workspace(tmp_path)
    repository = database.document_workbench_repository
    section = document["sections"][0]

    service.save(1, {"resource_id": section["id"], "content": "Before {{ helper }} After"})
    current = next(
        item for item in service.state(1)["documents"] if item["id"] == document["id"]
    )
    helper = current["sections"][0]["functions"][0]
    service.save(1, {"resource_id": helper["id"], "content": "extracted content"})

    pdf_renderer = _Renderer()
    DocumentWorkbenchRenderer(repository, renderer=pdf_renderer).generate(
        1,
        document["id"],
        _context(),
        output_directory=tmp_path,
    )

    section_value = _section_request_value(repository, document["id"], pdf_renderer.requests[0])
    assert section_value.content == "Before extracted content After"
