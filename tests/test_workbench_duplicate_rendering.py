from __future__ import annotations

from pathlib import Path

from jaw.application.document_workbench_render import DocumentWorkbenchRenderer
from jaw.application.document_workbench_service import DocumentWorkbenchService
from jaw.database import JobDatabase
from jaw.documents.contracts import DocumentRenderResult
from jaw.documents.workbench_symbols import reference_jinja_symbol


class _UserData:
    def read(self, *, user_id: int | None = None):
        return {"user": {"first_name": "Jane", "last_name": "Engineer"}}


class _Renderer:
    name = "tectonic"
    available = True

    def __init__(self) -> None:
        self.requests = []

    def render(self, request):
        self.requests.append(request)
        return DocumentRenderResult(
            pdf_bytes=b"%PDF-duplicate-references",
            rendered_source=request.template_source,
            diagnostics=(),
            renderer=self.name,
            command=("fake",),
            duration_ms=1,
        )


def test_case_variants_are_independent_reference_occurrences(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(
        1,
        {
            "name": "Case Variants",
            "template_source": "{{ section }}|{{ Section }}|{{ SECTION }}",
        },
    )

    assert [item["reference_symbol"] for item in document["sections"]] == [
        "section",
        "Section",
        "SECTION",
    ]
    assert len({item["id"] for item in document["sections"]}) == 3
    assert len({item["reference_id"] for item in document["sections"]}) == 3

    for section, content in zip(document["sections"], ("lower", "title", "upper"), strict=True):
        service.save(1, {"resource_id": section["id"], "content": content})

    fake = _Renderer()
    DocumentWorkbenchRenderer(repository, renderer=fake).generate(
        1,
        document["id"],
        {
            "user": {},
            "job": {},
            "work_history": [],
            "capabilities": {},
            "system": {},
        },
        output_directory=tmp_path,
    )

    edges = repository.list_edges(1, document["id"])
    request = fake.requests[0]
    keys = [reference_jinja_symbol(edge["id"]) for edge in edges]
    assert len(set(keys)) == 3
    assert [request.context[key].content for key in keys] == ["lower", "title", "upper"]
    assert request.template_source == "|".join(f"{{{{ {key} }}}}" for key in keys)


def test_identical_visible_symbols_can_target_different_resources(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(
        1,
        {
            "name": "Identical Symbols",
            "template_source": "{{ body }}\n{{ body }}\n{{ body }}",
        },
    )

    sections = document["sections"]
    assert [item["reference_symbol"] for item in sections] == ["body", "body", "body"]
    assert len({item["id"] for item in sections}) == 3
    assert len({item["reference_id"] for item in sections}) == 3


def test_duplicate_function_symbols_render_different_function_resources(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository
    service = DocumentWorkbenchService(repository, _UserData())
    document = service.create_document(
        1,
        {
            "name": "Duplicate Functions",
            "template_source": "{{ section }}",
        },
    )
    section = document["sections"][0]
    service.save(
        1,
        {
            "resource_id": section["id"],
            "content": "{{ helper() }}|{{ helper() }}",
        },
    )
    current = next(
        item for item in service.state(1)["documents"] if item["id"] == document["id"]
    )
    functions = current["sections"][0]["functions"]
    assert [item["reference_symbol"] for item in functions] == ["helper", "helper"]
    assert len({item["id"] for item in functions}) == 2
    assert len({item["reference_id"] for item in functions}) == 2

    service.save(1, {"resource_id": functions[0]["id"], "content": "First helper"})
    service.save(1, {"resource_id": functions[1]["id"], "content": "Second helper"})

    fake = _Renderer()
    DocumentWorkbenchRenderer(repository, renderer=fake).generate(
        1,
        document["id"],
        {
            "user": {},
            "job": {},
            "work_history": [],
            "capabilities": {},
            "system": {},
        },
        output_directory=tmp_path,
    )

    section_edge = repository.list_edges(1, document["id"])[0]
    section_key = reference_jinja_symbol(section_edge["id"])
    rendered_section = fake.requests[0].context[section_key]
    assert rendered_section.content == "First helper|Second helper"


def test_same_global_section_can_render_through_two_reference_jids(tmp_path: Path) -> None:
    database = JobDatabase(tmp_path / "jaw.db")
    repository = database.document_workbench_repository

    template = repository.create_resource(
        1,
        "template",
        name="Repeated Global",
        symbol="template",
        visibility="private",
        content="{{ shared }}|{{ shared }}",
        settings={"renderer": "tectonic", "format": "latex_jinja"},
    )
    document = repository.create_document(
        1,
        "Repeated Global",
        template["id"],
        output_pattern="Repeated Global.pdf",
    )
    repository.update_resource(1, template["id"], owner_id=document["id"])
    shared = repository.create_resource(
        1,
        "section",
        symbol="shared",
        visibility="global",
        content="Shared body",
        settings={"content_shape": "paragraphs"},
    )
    first = repository.link(
        1,
        document["id"],
        shared["id"],
        edge_kind="section",
        symbol="shared",
        sort_order=0,
    )
    second = repository.link(
        1,
        document["id"],
        shared["id"],
        edge_kind="section",
        symbol="shared",
        sort_order=1,
    )

    fake = _Renderer()
    DocumentWorkbenchRenderer(repository, renderer=fake).generate(
        1,
        document["id"],
        {
            "user": {},
            "job": {},
            "work_history": [],
            "capabilities": {},
            "system": {},
        },
        output_directory=tmp_path,
    )

    request = fake.requests[0]
    first_key = reference_jinja_symbol(first["id"])
    second_key = reference_jinja_symbol(second["id"])
    assert first_key != second_key
    assert request.context[first_key].content == "Shared body"
    assert request.context[second_key].content == "Shared body"
    assert request.template_source == f"{{{{ {first_key} }}}}|{{{{ {second_key} }}}}"
