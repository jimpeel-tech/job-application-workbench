from jaw.explicit_location import analyze_explicit_location
from jaw.parser_resolution import resolve_parser_evidence


def test_location_header_remote_us_extracts_country():
    evidence = analyze_explicit_location(
        "Location\nThis is a remote role based in the U.S.\nAbout the role"
    )

    assert evidence.value == "United States"
    assert evidence.rule == "location_header"


def test_location_header_onsite_city_state_name_extracts_geography():
    evidence = analyze_explicit_location(
        "Location\nThis is an onsite role at Portland, Oregon.\nAbout the job"
    )

    assert evidence.value == "Portland, Oregon"


def test_job_type_location_section_extracts_city_state():
    evidence = analyze_explicit_location(
        "Job Type & Location\nThis is a Permanent position based out of Austin, TX."
    )

    assert evidence.value == "Austin, TX"


def test_top_metadata_city_state_country_is_location():
    evidence = analyze_explicit_location(
        "Vorys\nSenior DevOps Engineer\nFull Time Regular\nStaff - Exempt\n"
        "Cincinnati, OH, US\n6 days ago"
    )

    assert evidence.value == "Cincinnati, OH"
    assert evidence.rule == "top_location_metadata"


def test_top_street_address_uses_trailing_city_state():
    evidence = analyze_explicit_location(
        "Versant\nSr. Site Reliability Engineer\n"
        "7580 Golf Channel Drive, Orlando, FL\nEmployees can work remotely"
    )

    assert evidence.value == "Orlando, FL"


def test_top_street_address_normalizes_full_state_name():
    evidence = analyze_explicit_location(
        "Versant\nSr. Platform Ops Engineer\n"
        "900 Sylvan Avenue, Englewood Cliffs, NEW JERSEY\nEmployees can work remotely"
    )

    assert evidence.value == "Englewood Cliffs, NJ"


def test_top_country_arrangement_badge_extracts_country_only():
    evidence = analyze_explicit_location(
        "ByteSearch\nSenior Platform Engineer\nUSA | Remote\n$180K-$230K"
    )

    assert evidence.value == "United States"
    assert evidence.rule == "top_location_metadata"


def test_remote_us_canada_scope_extracts_both_countries():
    evidence = analyze_explicit_location(
        "Leading CNCF Start Up Hiring for Senior SRE | Up to $200k + Equity | Remote (US/Canada)"
    )

    assert evidence.value == "United States or Canada"
    assert evidence.rule == "remote_us_canada_scope"


def test_remote_us_timezone_title_extracts_geographic_constraint():
    evidence = analyze_explicit_location(
        "Senior Site Reliability Engineer, Platform & Cloud FinOps "
        "(100% Remote - USA Central & EST)"
    )

    assert evidence.value == "United States, Central or Eastern Time"
    assert evidence.rule == "remote_us_timezone_scope"


def test_office_city_can_infer_state_from_explicit_company_location():
    evidence = analyze_explicit_location(
        "Founded in 2020 and headquartered in Redwood City, California.\n"
        "3 days onsite at the Redwood City office\n"
        "We are seeking an exceptional engineer."
    )

    assert evidence.value == "Redwood City, CA"
    assert evidence.rule == "office_city_with_inferred_state"


def test_based_full_time_in_nyc_normalizes_city():
    evidence = analyze_explicit_location(
        "What You Can Expect\nBased full-time in NYC, where the team works in-person"
    )

    assert evidence.value == "New York City, NY"


def test_us_residence_requirement_extracts_country():
    evidence = analyze_explicit_location(
        "Must reside in the U.S.; we are unable to provide visa sponsorship at this time"
    )

    assert evidence.value == "United States"
    assert evidence.rule == "us_residence_requirement"


def test_us_live_work_scope_preserves_hawaii_exclusion():
    evidence = analyze_explicit_location(
        "As a virtual first company, team members can live and work anywhere in the "
        "United States, with the exception of Hawaii."
    )

    assert evidence.value == "United States, excluding Hawaii"
    assert evidence.rule == "us_live_work_exclusion"


def test_us_hiring_scope_preserves_hawaii_exclusion():
    evidence = analyze_explicit_location(
        "Rula is a remote-first company. We currently hire in most U.S. states, "
        "with the exception of Hawaii."
    )

    assert evidence.value == "United States, excluding Hawaii"
    assert evidence.rule == "us_hiring_exclusion"


def test_us_based_scope_preserves_not_hiring_in_hawaii():
    evidence = analyze_explicit_location(
        "100% remote work environment (must be based in United States, "
        "currently not hiring in Hawaii)"
    )

    assert evidence.value == "United States, excluding Hawaii"
    assert evidence.rule == "us_based_exclusion"


def test_research_institution_location_extracts_physical_site():
    evidence = analyze_explicit_location(
        "This premier research institution, located near Knoxville in Oak Ridge, TN, "
        "addresses national needs. This position can be remote, but requires onsite visits."
    )

    assert evidence.value == "Oak Ridge, TN"
    assert evidence.rule == "explicit_site_location"


def test_company_headquarters_alone_is_not_job_location():
    evidence = analyze_explicit_location(
        "Example Corp\nPlatform Engineer\n"
        "The company is headquartered in Seattle, Washington.\n"
        "This role supports customers around the world."
    )

    assert evidence.value == ""


def test_richer_work_arrangement_location_still_wins_in_resolution():
    resolution = resolve_parser_evidence(
        [],
        "Location: remote - Austin,TX\n"
        "Our headquarters are in Cincinnati, OH.",
    )

    assert resolution.values["location"] == ("Austin, TX",)
    assert resolution.fields["location"].priority == 95
