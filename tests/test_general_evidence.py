from jaw.general_evidence import (
    extract_application_deadline_evidence,
    extract_clearance_evidence,
    extract_company_evidence,
    extract_employment_type_evidence,
    extract_on_call_evidence,
    extract_sponsorship_evidence,
    extract_travel_evidence,
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


def test_oracle_full_time_prose_is_employment_type():
    evidence = extract_employment_type_evidence(
        "This position will be full-time on-site at Oracle's offices located in Nashville, TN."
    )

    assert evidence is not None
    assert evidence.value == "Full-time"


def test_contract_length_contract_to_hire_is_employment_type():
    evidence = extract_employment_type_evidence(
        "Contract Length: 6-Months Contract to Hire"
    )

    assert evidence is not None
    assert evidence.value == "Contract to hire"


def test_compact_metadata_full_time_is_employment_type():
    evidence = extract_employment_type_evidence(
        "Sr.DevOps Engineer\nHybrid/Remote · Full Time · Experience: 3-4 years"
    )

    assert evidence is not None
    assert evidence.value == "Full-time"


def test_full_time_exempt_position_preserves_modifier():
    evidence = extract_employment_type_evidence(
        "This is a full-time, exempt position that reports to the Senior Director."
    )

    assert evidence is not None
    assert evidence.value == "Full-time, exempt"


def test_plural_job_types_preserve_full_time_or_contract_alternative():
    evidence = extract_employment_type_evidence("Job Types: Full-time, Contract")

    assert evidence is not None
    assert evidence.value == "Full-time or contract"


def test_generic_type_label_can_capture_hourly_contract():
    evidence = extract_employment_type_evidence(
        "Position: Site Reliability Engineer\nType: Hourly contract\nCompensation: $40 - $70/hour"
    )

    assert evidence is not None
    assert evidence.value == "Hourly contract"


def test_regular_employee_multiline_job_type_is_preserved():
    evidence = extract_employment_type_evidence(
        "Job Type\nRegular Employee\nDoes this position require a security clearance?\nNo"
    )

    assert evidence is not None
    assert evidence.value == "Regular employee"


def test_permanent_full_time_role_is_preserved():
    evidence = extract_employment_type_evidence(
        "We are unable to sponsor for this permanent full-time role."
    )

    assert evidence is not None
    assert evidence.value == "Permanent, full-time"


def test_contract_full_time_label_is_combined_employment_type():
    evidence = extract_employment_type_evidence(
        "Employment Type: Contract — Full-Time\nDepartment: Engineering"
    )

    assert evidence is not None
    assert evidence.value == "Full-time contract"


def test_benefit_type_salaried_full_time_is_employment_type():
    evidence = extract_employment_type_evidence(
        "Job ID 2026-14214 Benefit Type Salaried High Fringe/Full-Time\nOverview"
    )

    assert evidence is not None
    assert evidence.value == "Full-time salaried"


def test_full_time_experience_requirement_is_not_employment_type():
    evidence = extract_employment_type_evidence(
        "1+ years of professional full-time experience preferred, but not required"
    )

    assert evidence is None


def test_clearance_question_answer_no_is_preserved():
    evidence = extract_clearance_evidence(
        "Does this position require a security clearance?\nNo"
    )

    assert evidence is not None
    assert evidence.value == "No"


def test_specific_clearance_list_beats_generic_title_clearance():
    evidence = extract_clearance_evidence(
        "IT Network Engineer - Top Secret Clearance\n"
        "Active Top Secret, Top Secret SCI, or DOE Level Q clearance\n"
        "Active Top Secret or TS/SCI with Polygraph."
    )

    assert evidence is not None
    assert evidence.value == "Active Top Secret, Top Secret SCI, or DOE Level Q clearance"


def test_oracle_sponsorship_not_available_is_preserved():
    evidence = extract_sponsorship_evidence(
        "Visa / work permit sponsorship is not available for this position"
    )

    assert evidence is not None
    assert evidence.value == "Not offered"


def test_frost_cannot_sponsor_or_transfer_is_preserved():
    evidence = extract_sponsorship_evidence(
        "Immigration Sponsorship: Unfortunately, we currently are not able to sponsor "
        "or transfer a sponsorship to Frost. This includes H-1B, TN, OPT, O-1, L-1."
    )

    assert evidence is not None
    assert evidence.value == "Not offered"


def test_less_than_travel_percent_is_preserved():
    evidence = extract_travel_evidence(
        "Must be willing to do some travel domestically and globally (<10%) in the future as needed"
    )

    assert evidence is not None
    assert evidence.value == "<10%"


def test_applications_accepted_at_least_until_extracts_deadline():
    evidence = extract_application_deadline_evidence(
        "Applications for this job will be accepted at least until September 14, 2026."
    )

    assert evidence is not None
    assert evidence.value == "September 14, 2026"


def test_general_evidence_overrides_legacy_company_and_on_call_guesses():
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


def test_general_evidence_resolves_remaining_decision_fields():
    resolution = resolve_parser_evidence(
        [],
        (
            "Contract Length: 6-Months Contract to Hire\n"
            "Visa / work permit sponsorship is not available for this position\n"
            "Active Top Secret, Top Secret SCI, or DOE Level Q clearance\n"
            "Must be willing to do some travel domestically and globally (<10%)\n"
            "Applications for this job will be accepted at least until September 14, 2026."
        ),
    )

    assert resolution.values["employment_type"] == ("Contract to hire",)
    assert resolution.values["sponsorship"] == ("Not offered",)
    assert resolution.values["clearance"] == (
        "Active Top Secret, Top Secret SCI, or DOE Level Q clearance",
    )
    assert resolution.values["travel"] == ("<10%",)
    assert resolution.values["application_deadline"] == ("September 14, 2026",)
