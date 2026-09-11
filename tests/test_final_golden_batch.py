from jaw.ats_location_evidence import analyze_ats_locations
from jaw.explicit_on_call import analyze_explicit_on_call
from jaw.explicit_title import analyze_explicit_title
from jaw.parser_resolution import resolve_parser_evidence
from jaw.value_canonicalization import canonical_capture_value
from jaw.work_arrangement_enrichment import analyze_enriched_work_arrangement


def test_part_of_on_call_rotation_is_required():
    evidence = analyze_explicit_on_call(
        "The employee will be part of an on-call rotation. The current rotation is 1 week every 5 weeks."
    )

    assert evidence.value == "Required"
    assert evidence.rule == "part_of_on_call_rotation"


def test_linkedin_company_header_keeps_posted_title_over_body_title():
    title = analyze_explicit_title(
        "Company logo for, BMO U.S..\n"
        "BMO U.S.\n\n"
        "Principal Cloud Engineer Azure\n\n"
        "Texas, United States · 1 week ago\n\n"
        "About the job\n"
        "As a Principal Azure Platform Engineer, you will play a hands-on role."
    )

    assert title.value == "Principal Cloud Engineer Azure"
    assert title.rule == "posting_header_title"


def test_first_line_posting_title_beats_role_name_in_body():
    title = analyze_explicit_title(
        "Program Manager\n"
        "Remote - US ; United States; Wichita, Kansas, United States; "
        "Morrisville, North Carolina, United States\n"
        "Job category: Business Operations\n"
        "Job ID: 136023-en_US\n\n"
        "Job Summary\n"
        "As a Product Structure & Pricing Operations Manager, you will lead a team."
    )

    assert title.value == "Program Manager"


def test_terminal_company_period_is_comparison_equivalent():
    assert canonical_capture_value("company", "BMO U.S.") == canonical_capture_value(
        "company", "BMO U.S"
    )


def test_state_country_header_is_posting_location():
    locations = analyze_ats_locations(
        "Principal Cloud Engineer Azure\nTexas, United States · 1 week ago\nAbout the job"
    )

    assert tuple(item.value for item in locations) == ("Texas, United States",)


def test_city_country_uses_compensation_state_when_header_omits_state():
    locations = analyze_ats_locations(
        "Senior Data Scientist\n"
        "Data Science | San Jose, United States | ID: 11173\n\n"
        "What is the role?\n"
        "For California Only - The estimated annual salary is $169,900 - $195,000."
    )

    assert tuple(item.value for item in locations) == ("San Jose, CA",)


def test_remote_us_multilocation_header_splits_posting_locations():
    locations = analyze_ats_locations(
        "Program Manager\n"
        "Remote - US ; United States; Wichita, Kansas, United States; "
        "Morrisville, North Carolina, United States\n"
        "Job category: Business Operations\n"
        "Job ID: 136023-en_US\n\n"
        "Job Summary"
    )

    assert tuple(item.value for item in locations) == (
        "United States",
        "Wichita, KS",
        "Morrisville, NC",
    )


def test_explicit_remote_territory_emits_each_state_as_remote_eligibility():
    analysis = analyze_enriched_work_arrangement(
        "Enterprise Solutions Engineer - Alabama, Mississippi, Louisiana\n"
        "United States\n\n"
        "LOCATION\n"
        "This is a remote position; however, candidates must be based in "
        "Mississippi, Alabama, or Louisianna to effectively support customers.\n"
        "At NetApp, we embrace a hybrid working environment for all employees."
    )

    assert analysis.status == "Remote"
    eligible = {
        item.location
        for item in analysis.evidence
        if item.location_relation == "remote_eligibility"
    }
    assert {"Mississippi", "Alabama", "Louisiana"} <= eligible


def test_remote_us_multilocation_has_no_single_primary_work_location():
    analysis = analyze_enriched_work_arrangement(
        "Program Manager\n"
        "Remote - US ; United States; Wichita, Kansas, United States; "
        "Morrisville, North Carolina, United States\n"
        "Job Summary\nBody"
    )

    assert analysis.status == "Remote"
    assert analysis.location == ""
    assert any(
        item.location == "United States"
        and item.location_relation == "remote_eligibility"
        for item in analysis.evidence
    )


def test_program_manager_multilocation_flows_through_parser_resolution():
    resolution = resolve_parser_evidence(
        [],
        "Program Manager\n"
        "Remote - US ; United States; Wichita, Kansas, United States; "
        "Morrisville, North Carolina, United States\n"
        "Job category: Business Operations\n"
        "Job ID: 136023-en_US\n\n"
        "Job Summary\n"
        "As a Product Structure & Pricing Operations Manager, you will lead a team.",
    )

    assert resolution.values["title"] == ("Program Manager",)
    assert resolution.values["remote_status"] == ("Remote",)
    assert resolution.values["location"] == (
        "United States",
        "Wichita, KS",
        "Morrisville, NC",
    )
