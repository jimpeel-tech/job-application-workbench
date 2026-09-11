from jaw.job_id_evidence import analyze_job_id
from jaw.parser_resolution import resolve_parser_evidence
from jaw.posting_metadata_evidence import (
    extract_posting_metadata_evidence,
    is_location_like_company_candidate,
)


def test_blank_ref_id_does_not_consume_following_prose():
    content = (
        "Distinguished Architect, Engineering Excellence\n"
        "Santa Clara, California, United States of America\n"
        "IT\n"
        "Ref ID:\n\n"
        "Our Mission\n"
        "At Palo Alto Networks®, we’re united by a shared mission."
    )

    evidence = analyze_job_id(content)
    resolution = resolve_parser_evidence([], content)

    assert evidence.value == ""
    assert resolution.values["job_id"] == ()


def test_ref_id_on_immediate_next_line_is_preserved():
    evidence = analyze_job_id("Ref ID:\nJR-022046\nApply")

    assert evidence.value == "JR-022046"
    assert evidence.rule == "explicit_job_id_label"


def test_explicit_sponsorship_eligibility_yes_is_available():
    evidence = extract_posting_metadata_evidence(
        "Is role eligible for Immigration Sponsorship?: Yes"
    )

    sponsorship = next(item for item in evidence if item.field == "sponsorship")
    assert sponsorship.value == "Available"


def test_company_prose_with_trademark_is_explicit_company_evidence():
    evidence = extract_posting_metadata_evidence(
        "At Palo Alto Networks®, we’re united by a shared mission."
    )

    company = next(item for item in evidence if item.field == "company")
    assert company.value == "Palo Alto Networks"


def test_full_country_location_is_not_a_company_candidate():
    assert is_location_like_company_candidate(
        "Santa Clara, California, United States of America"
    )
    assert not is_location_like_company_candidate("Palo Alto Networks")


def test_posting_metadata_overrides_legacy_location_company_guess():
    content = (
        "Staff IT Software Engineer\n"
        "Santa Clara, California, United States of America\n"
        "IT\n"
        "Ref ID:\nJR-022046\n\n"
        "At Palo Alto Networks®, we’re united by a shared mission.\n"
        "Is role eligible for Immigration Sponsorship?: Yes"
    )
    resolution = resolve_parser_evidence(
        [
            {
                "capture_context": "job_description",
                "fields": {
                    "company": "Santa Clara, California, United States of America",
                },
            }
        ],
        content,
    )

    assert resolution.values["company"] == ("Palo Alto Networks",)
    assert resolution.values["sponsorship"] == ("Available",)
    assert resolution.values["job_id"] == ("JR-022046",)
