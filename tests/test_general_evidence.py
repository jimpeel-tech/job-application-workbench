from jaw.general_evidence import (
    extract_company_evidence,
    extract_on_call_evidence,
)
from jaw.parser_resolution import resolve_parser_evidence


def test_servicenow_company_and_on_call_practices_are_distinguished():
    content = (
        "Today, ServiceNow is the AI control tower for business reinvention.\n"
        "You will be accountable for reliability, establishing SLOs, on-call practices, "
        "and operational reviews."
    )

    company = extract_company_evidence(content)
    on_call = extract_on_call_evidence(content)

    assert company is not None
    assert company.value == "ServiceNow"
    assert on_call is None


def test_location_header_does_not_become_company_when_oracle_is_explicit_in_prose():
    content = (
        "Senior Reliability Engineer - Electrical (Nashville, TN on-site)\n"
        "Nashville, TN, United States\n"
        "This position will be full-time on-site at Oracle's offices located in Nashville, TN.\n"
        "Oracle US offers a comprehensive benefits package."
    )

    company = extract_company_evidence(content)

    assert company is not None
    assert company.value == "Oracle"


def test_spacex_founded_language_identifies_company_not_location():
    content = (
        "IT Network Engineer - Top Secret Clearance\n"
        "Hawthorne, CA\n"
        "SpaceX was founded under the belief that humanity should explore the stars."
    )

    company = extract_company_evidence(content)

    assert company is not None
    assert company.value == "SpaceX"


def test_linkedin_company_logo_prefix_is_cleaned():
    company = extract_company_evidence(
        "Company logo for, Addison Group.\nAddison Group\nLead Cloud DevOps Engineer"
    )

    assert company is not None
    assert company.value == "Addison Group"


def test_explicit_on_call_participation_is_required():
    on_call = extract_on_call_evidence(
        "This role participates in an on-call rotation for production incidents."
    )

    assert on_call is not None
    assert on_call.value == "Required"


def test_must_be_available_for_on_call_rotations_is_required():
    on_call = extract_on_call_evidence("Must be available for on-call rotations.")

    assert on_call is not None
    assert on_call.value == "Required"


def test_explicit_no_on_call_is_preserved():
    on_call = extract_on_call_evidence("There is no on-call rotation for this role.")

    assert on_call is not None
    assert on_call.value == "Not required"


def test_general_evidence_overrides_legacy_company_and_suppresses_weak_on_call_guess():
    resolution = resolve_parser_evidence(
        [
            {
                "capture_context": "company",
                "fields": {"company": "Company logo for, Addison Group."},
            },
            {
                "capture_context": "job_description",
                "fields": {"on_call": "Required"},
            },
        ],
        (
            "Company logo for, Addison Group.\nAddison Group\n"
            "The manager will establish on-call practices for the team."
        ),
    )

    assert resolution.values["company"] == ("Addison Group",)
    assert resolution.values["on_call"] == ()
    assert resolution.fields["company"].priority == 105


def test_general_evidence_preserves_explicit_on_call_requirement_in_resolution():
    resolution = resolve_parser_evidence(
        [],
        "Platform Engineer\nThis role participates in an on-call rotation.",
    )

    assert resolution.values["on_call"] == ("Required",)
    assert resolution.fields["on_call"].priority == 95
