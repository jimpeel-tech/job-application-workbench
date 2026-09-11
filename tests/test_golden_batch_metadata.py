from jaw.ats_location_evidence import analyze_ats_locations
from jaw.job_id_evidence import analyze_job_id
from jaw.parser_resolution import resolve_parser_evidence
from jaw.work_arrangement_enrichment import analyze_enriched_work_arrangement


def test_collapsed_ats_job_ids_are_detected():
    cases = {
        "ResearchJob IdR170796Posted Date 07/31/2026": "R170796",
        "CategoryInformation TechnologyJob IdR171012Posted Date 08/25/2026": "R171012",
        "Mississauga, Ontario, Canada CategoryTechnology Posted Date07/29/2026 Job Id26009410": "26009410",
        "Ref ID:\nJR-019711\nApply": "JR-019711",
    }

    for content, expected in cases.items():
        assert analyze_job_id(content).value == expected


def test_ats_locations_support_us_canada_and_multi_location_headers():
    adobe = analyze_ats_locations(
        "Sr. Research Engineer\n"
        "ResearchJob IdR170796Posted Date 07/31/2026\n"
        "Job available in 2 locations\n"
        " San Francisco, California, United States of America "
        "San Jose, California, United States of America\n\n"
        "The Opportunity\nBody"
    )
    canada = analyze_ats_locations(
        "Machine Learning Engineer - Express Scripts Canada\n\n"
        "Mississauga, Ontario, Canada CategoryTechnology Posted Date07/29/2026"
    )
    seattle = analyze_ats_locations(
        "Research Scientist/Engineer\n"
        "Location Seattle, Washington, United States of AmericaCategoryResearch"
    )

    assert tuple(item.value for item in adobe) == ("San Francisco, CA", "San Jose, CA")
    assert tuple(item.value for item in canada) == ("Mississauga, Ontario, Canada",)
    assert tuple(item.value for item in seattle) == ("Seattle, WA",)


def test_explicit_job_metadata_resolves_express_scripts_canada_fixture_shape():
    resolution = resolve_parser_evidence(
        [
            {
                "capture_context": "job_title",
                "fields": {"title": "Machine Learning Engineer - Express Scripts Canada"},
            }
        ],
        "Machine Learning Engineer - Express Scripts Canada\n\n"
        "Mississauga, Ontario, Canada CategoryTechnology Posted Date07/29/2026 "
        "Job Id26009410\n"
        "Job Description\n"
        "Job Title: Machine Learning Engineer\n\n"
        "Location: Mississauga\n"
        "Employment Type: Full-time\n"
        "Work Arrangement: Hybrid\n"
        "Pay Range: $115,000 - $125,000 annually\n"
        "It will be a condition of employment that the successful candidate obtains an "
        "Enhanced Reliability Clearance from the Federal Government.",
    )

    assert resolution.values["title"] == ("Machine Learning Engineer",)
    assert resolution.values["job_id"] == ("26009410",)
    assert resolution.values["location"] == ("Mississauga, Ontario, Canada",)
    assert resolution.values["remote_status"] == ("Hybrid",)
    assert resolution.values["pay"] == ("CAD 115000–125000 per year",)
    assert resolution.values["clearance"] == ("Enhanced Reliability Clearance",)


def test_explicit_work_arrangement_label_keeps_posting_location_relation():
    analysis = analyze_enriched_work_arrangement(
        "Machine Learning Engineer\n"
        "Mississauga, Ontario, Canada CategoryTechnology\n"
        "Job Description\n"
        "Location: Mississauga\n"
        "Work Arrangement: Hybrid"
    )

    assert analysis.status == "Hybrid"
    assert analysis.location == "Mississauga, Ontario, Canada"
    assert any(
        item.location == "Mississauga, Ontario, Canada"
        and item.location_relation == "posting_location"
        for item in analysis.evidence
    )


def test_roku_weekday_office_policy_is_hybrid_not_remote_only():
    analysis = analyze_enriched_work_arrangement(
        "What's Roku's approach to hybrid working?\n"
        "Roku fosters an inclusive and collaborative environment where teams generally "
        "work in the office Monday through Thursday. Fridays are generally flexible for "
        "remote work, except for employees whose specific roles or assigned office location "
        "require five days' a week attendance."
    )

    assert analysis.status == "Hybrid"
    assert analysis.conflict is False


def test_generic_full_time_office_policy_is_not_promoted_to_role_arrangement():
    analysis = analyze_enriched_work_arrangement(
        "We believe collaboration thrives in person. That's why most of our teams work "
        "from the office full time, with flexibility when it's needed."
    )

    assert analysis.status == ""
    assert analysis.evidence == ()


def test_hybrid_cloud_remains_technical_not_workplace_evidence():
    analysis = analyze_enriched_work_arrangement(
        "The team delivers services from Adobe's hybrid-cloud environment."
    )

    assert analysis.status == ""
    assert analysis.evidence == ()


def test_parser_returns_multiple_explicit_ats_locations_in_source_order():
    resolution = resolve_parser_evidence(
        [],
        "Senior Delivery Manager, Enterprise Productivity\n"
        "CategoryInformation TechnologyJob IdR171012Posted Date 08/25/2026\n"
        "Job available in 2 locations\n"
        " San Jose, California, United States of America "
        "Ottawa, Ontario, Canada\n\n"
        "The Opportunity\nBody",
    )

    assert resolution.values["job_id"] == ("R171012",)
    assert resolution.values["location"] == ("San Jose, CA", "Ottawa, Ontario, Canada")
