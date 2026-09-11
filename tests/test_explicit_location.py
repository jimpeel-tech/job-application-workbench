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

    assert evidence.value == "Portland, OR"


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
