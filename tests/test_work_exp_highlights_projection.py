from __future__ import annotations

from jaw.documents.context import GenerationContext
from jaw.documents.expression_context import build_expression_catalog, normalize_highlights


def test_normalize_highlights_splits_line_boundaries_and_strips_list_markers():
    raw = (
        "  • Built Kubernetes platform  \r\n"
        "\t- Reduced deployment toil\r"
        "* Automated infrastructure\n"
        "→ Improved rollout safety\u2028"
        "▪ Supported global scale\u2029"
        "\n"
        "•\n"
        ".NET platform engineering\n"
        "C++ development\n"
        "$200K annual savings\n"
        "100% automated"
    )

    assert normalize_highlights(raw) == [
        "Built Kubernetes platform",
        "Reduced deployment toil",
        "Automated infrastructure",
        "Improved rollout safety",
        "Supported global scale",
        ".NET platform engineering",
        "C++ development",
        "$200K annual savings",
        "100% automated",
    ]


def test_expression_catalog_projects_highlights_without_mutating_stored_text():
    stored_highlights = "  • First accomplishment  \n\n  - Second accomplishment  "
    work_history = {
        "id": "work_1",
        "enabled": True,
        "company": "Example Employer",
        "title": "Example Role",
        "highlights": stored_highlights,
    }
    user_state = {
        "user": {},
        "work_history": [work_history],
        "capability_model": {},
    }

    catalog = build_expression_catalog(user_state, {})

    assert catalog["work_exp"][0]["highlights"] == [
        "First accomplishment",
        "Second accomplishment",
    ]
    assert work_history["highlights"] == stored_highlights


def test_generation_context_normalizes_prebuilt_work_exp_highlights():
    context = GenerationContext.from_mapping(
        {
            "context_schema_version": 2,
            "work_exp": [
                {
                    "company": "Example Employer",
                    "highlights": "• First example\nSecond example",
                }
            ],
        },
        source="test",
    )

    assert context.work_exp[0]["highlights"] == [
        "First example",
        "Second example",
    ]


def test_normalize_highlights_accepts_already_structured_lists():
    assert normalize_highlights(
        [
            "• First item",
            "Second item\nThird item",
            "  - Fourth item  ",
        ]
    ) == [
        "First item",
        "Second item",
        "Third item",
        "Fourth item",
    ]
