import pytest

from jaw.documents import DocumentRenderError, render_latex_template


def test_runtime_type_error_is_wrapped_as_document_render_error():
    template = "{% for item in value %}{{ item }}{% endfor %}"

    with pytest.raises(
        DocumentRenderError,
        match="TypeError: 'NoneType' object is not iterable",
    ) as failure:
        render_latex_template(template, {"value": None}, autoescape_text=True)

    diagnostic = failure.value.diagnostics[0]
    assert diagnostic.source == "jinja2"
    assert diagnostic.message == "TypeError: 'NoneType' object is not iterable"
