from importlib.resources import files

from jinja2 import meta

from jaw.documents import render_latex_template
from jaw.documents.context import ExampleContextProvider
from jaw.documents.latex import latex_environment
from jaw.documents.workbench_symbols import referenced_symbols

_TEMPLATE_NAMES = ("quick_reference.tex.j2", "sandbox.tex.j2")
_RETIRED_ROOTS = {
    "candidate_name",
    "position_name",
    "work_history",
    "capabilities",
    "work_experience",
}


def _source(name: str) -> str:
    return (
        files("jaw")
        .joinpath("resources")
        .joinpath("documents")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )


def test_builtin_runtime_templates_use_only_documents_v2_roots() -> None:
    environment = latex_environment(autoescape_text=True)
    for name in _TEMPLATE_NAMES:
        source = _source(name)
        assert "job_ref" in source
        assert "work_exp" in source
        assert "cap" in source
        undeclared = meta.find_undeclared_variables(environment.parse(source))
        assert not (_RETIRED_ROOTS & undeclared)
        assert referenced_symbols(source) == []


def test_builtin_runtime_templates_render_with_example_context() -> None:
    context = ExampleContextProvider(1).load().template_context()

    quick_reference = render_latex_template(
        _source("quick_reference.tex.j2"),
        context,
        autoescape_text=True,
    )
    sandbox = render_latex_template(
        _source("sandbox.tex.j2"),
        context,
        autoescape_text=True,
    )

    assert "Example User" in quick_reference
    assert "Example Title" in quick_reference
    assert "Example Skill 1" in quick_reference
    assert "Example work-history evidence 1." in quick_reference
    assert "Example User" in sandbox
    assert "Example Company" in sandbox
    assert "Example Skill 1" in sandbox
