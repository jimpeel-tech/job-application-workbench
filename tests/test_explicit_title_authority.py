from jaw.explicit_title import analyze_explicit_title
from jaw.parser_resolution import resolve_parser_values


def test_unlabeled_header_does_not_override_job_title_capture():
    values = resolve_parser_values(
        [
            {
                "capture_context": "job_description",
                "fields": {"title": "Software Engineer"},
            },
            {
                "capture_context": "job_title",
                "fields": {"title": "Senior Platform Engineer"},
            },
        ],
        "Software Engineer\nLong description text",
    )

    assert values["title"] == ("Senior Platform Engineer",)


def test_labeled_job_title_remains_high_confidence_explicit_evidence():
    explicit = analyze_explicit_title(
        "Job Title: Machine Learning Engineer\nExpress Scripts Canada"
    )

    assert explicit.value == "Machine Learning Engineer"
    assert explicit.rule == "explicit_job_title_label"


def test_ats_shaped_header_remains_high_confidence_title_evidence():
    explicit = analyze_explicit_title(
        "Program Manager\n"
        "Remote - US ; United States; Wichita, Kansas, United States\n"
        "Job category: Business Operations\n"
        "Job ID: 136023-en_US\n\n"
        "Job Summary\n"
        "As a Product Structure & Pricing Operations Manager, you will lead a team."
    )

    assert explicit.value == "Program Manager"
    assert explicit.rule == "posting_header_title"
