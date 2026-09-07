from importlib.resources import files

from jaw.application.document_workbench_render import SectionValue
from jaw.documents import render_latex_template
from jaw.documents.workbench_symbols import referenced_symbols


def _template_source() -> str:
    return (
        files("jaw")
        .joinpath("resources")
        .joinpath("documents")
        .joinpath("cover_letter.tex.j2")
        .read_text(encoding="utf-8")
    )


def test_cover_letter_uses_canonical_jaw_roots_and_workbench_sections() -> None:
    source = _template_source()

    assert "{{ user.full_name }}" in source
    assert "job_ref.title" in source
    assert "system.current_date" in source
    assert "| latex" not in source
    assert "candidate_name" not in source
    assert "position_name" not in source
    assert "paragraph.content" not in source
    assert "paragraph.enabled" not in source
    assert "system.greeting" not in source
    assert "system.signoff" not in source
    assert referenced_symbols(source) == ["greeting", "paragraphs", "signoff"]


def test_cover_letter_autoescapes_jaw_and_section_text_once() -> None:
    source = _template_source()
    paragraphs = SectionValue(
        content="Built R&D automation by 50% with foo_bar.",
        shape="paragraphs",
        values=("Built R&D automation by 50% with foo_bar.",),
    )
    rendered = render_latex_template(
        source,
        {
            "user": {
                "full_name": "Jane & Engineer",
                "phone_number": "555-0100",
                "email": "jane_r&d@example.com",
                "linkedin": "https://linkedin.com/in/jane_engineer",
                "portfolio": "https://example.com/r&d",
            },
            "job_ref": {"title": "Platform & SRE", "company": "Example & Sons"},
            "system": {"current_date": "August 19, 2026"},
            "greeting": "Dear R&D Team,",
            "paragraphs": paragraphs,
            "signoff": "Sincerely,",
        },
        autoescape_text=True,
    )

    assert r"Jane \& Engineer" in rendered
    assert "PLATFORM" in rendered
    assert r"\&" in rendered
    assert "SRE" in rendered
    assert r"Built R\&D automation by 50\% with foo\_bar." in rendered
    assert r"Dear R\&D Team," in rendered
    assert r"R\\\&D" not in rendered


def test_noncanonical_flat_fields_are_regular_workbench_symbols() -> None:
    source = """
{{ candidate_name }}
{{ position_name }}
{{ phone }}
{{ paragraphs }}
"""

    assert referenced_symbols(source) == [
        "candidate_name",
        "position_name",
        "phone",
        "paragraphs",
    ]
