from importlib.resources import files

from jinja2 import meta

from jaw.documents import render_latex_template
from jaw.documents.context import ExampleContextProvider
from jaw.documents.latex import latex_environment
from jaw.documents.workbench_symbols import referenced_symbols

_RETIRED_ROOTS = {
    "candidate_name",
    "position_name",
    "work_history",
    "capabilities",
    "work_experience",
}


def _source() -> str:
    return (
        files("jaw")
        .joinpath("resources")
        .joinpath("documents")
        .joinpath("quick_reference.tex.j2")
        .read_text(encoding="utf-8")
    )


def test_quick_reference_uses_only_documents_v2_roots() -> None:
    environment = latex_environment(autoescape_text=True)
    source = _source()

    assert "job_ref" in source
    assert "work_exp" in source
    assert "cap" in source
    undeclared = meta.find_undeclared_variables(environment.parse(source))
    assert not (_RETIRED_ROOTS & undeclared)
    assert referenced_symbols(source) == []


def test_quick_reference_renders_with_example_context() -> None:
    context = ExampleContextProvider(1).load().template_context()

    quick_reference = render_latex_template(
        _source(),
        context,
        autoescape_text=True,
    )

    assert "Example User" in quick_reference
    assert "Example Title" in quick_reference
    assert "Example Skill 1" in quick_reference
    assert "Example work-history evidence 1." in quick_reference
