from jaw.documents.workbench_symbols import referenced_symbols


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
