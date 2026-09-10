from __future__ import annotations

import json

from jaw.application import CaptureService
from jaw.capture_context import (
    capture_metrics,
    classify_capture_context,
    normalize_capture_for_parser,
)
from jaw.database import JobDatabase
from jaw.parser_resolution import resolve_parser_evidence
from jaw.work_arrangement import analyze_work_arrangement


def test_remote_country_badge_is_metadata_with_related_location():
    raw = "Remote - Switzerland"

    classification = classify_capture_context(raw, "job_capture")
    normalized = normalize_capture_for_parser(raw, classification.content_type)
    metrics = capture_metrics(raw, sequence=2)
    analysis = analyze_work_arrangement(raw)

    assert classification.content_type == "job_metadata"
    assert normalized == "Remote\nLocation: Switzerland"
    assert metrics["shape"] == "metadata_like"
    assert metrics["work_arrangement_signal"] is True
    assert analysis.status == "Remote"
    assert analysis.location == "Switzerland"
    assert analysis.conflict is False
    assert analysis.evidence[0].location_relation == "remote_eligibility"


def test_remote_country_badge_flows_through_capture_service(tmp_path):
    database = JobDatabase(tmp_path / "jaw.db")
    service = CaptureService(database)

    accepted = service.accept_text(7, "Remote - Switzerland")

    event = accepted.session["events"][-1]
    metadata = json.loads(event["metadata"])
    assert event["content"] == "Remote - Switzerland"
    assert event["content_type"] == "job_metadata"
    assert metadata["normalized_content"] == "Remote\nLocation: Switzerland"
    assert metadata["extraction"]["fields"]["remote_status"] == "Remote"
    assert metadata["extraction"]["fields"]["location"] == "Switzerland"


def test_hybrid_city_badge_marks_office_location():
    analysis = analyze_work_arrangement("Hybrid | Austin, TX")

    assert analysis.status == "Hybrid"
    assert analysis.location == "Austin, TX"
    assert analysis.evidence[0].location_relation == "office_location"


def test_remote_and_required_office_attendance_preserve_conflict():
    analysis = analyze_work_arrangement(
        "This is a remote role. Employees near Austin, TX are expected to work "
        "in the office 3 days per week."
    )

    assert analysis.status == "Conflicting remote claim"
    assert analysis.conflict is True
    assert analysis.location == "Austin, TX"
    assert {item.arrangement for item in analysis.evidence} == {"remote", "on-site"}
    office = next(item for item in analysis.evidence if item.arrangement == "on-site")
    assert office.location_relation == "office_location"
    assert office.frequency == "3 days per week"


def test_hybrid_prose_extracts_frequency_and_office_location():
    analysis = analyze_work_arrangement(
        "This hybrid role requires three days per week in our Austin, TX office."
    )

    assert analysis.status == "Hybrid"
    assert analysis.location == "Austin, TX"
    assert analysis.conflict is False
    assert analysis.evidence[0].frequency == "three days per week"
    assert analysis.evidence[0].location_relation == "office_location"


def test_it_terms_remote_access_and_hybrid_cloud_are_not_work_arrangements():
    analysis = analyze_work_arrangement(
        "Experience with remote access and hybrid cloud infrastructure is required."
    )

    assert analysis.status == ""
    assert analysis.evidence == ()


def test_remote_us_scope_is_remote_eligibility_not_office_location():
    analysis = analyze_work_arrangement("This position is remote anywhere in the United States.")

    assert analysis.status == "Remote"
    assert analysis.location == "United States"
    assert analysis.evidence[0].location_relation == "remote_eligibility"


def test_servicenow_flexible_header_uses_neighboring_posting_location():
    content = (
        "Engineering, Infrastructure and Operations\n"
        "San Diego\n"
        "Flexible\n"
        "September 04, 2026\n\n"
        "Work Personas\n"
        "Work personas (flexible, remote, or required in office) are categories assigned "
        "depending on the nature of the work."
    )

    analysis = analyze_work_arrangement(content)

    assert analysis.status == "Flexible"
    assert analysis.location == "San Diego"
    assert analysis.conflict is False


def test_location_row_remote_extracts_remote_eligibility():
    analysis = analyze_work_arrangement("Location: remote - Austin,TX")

    assert analysis.status == "Remote"
    assert analysis.location == "Austin, TX"
    assert analysis.evidence[0].location_relation == "remote_eligibility"


def test_periodic_office_attendance_without_remote_claim_is_hybrid():
    content = (
        "Candidates may live in San Antonio or Austin Texas areas. "
        "This role will require 2 to 3 days per month at the One Frost Corporate Campus "
        "office in San Antonio."
    )

    analysis = analyze_work_arrangement(content)

    assert analysis.status == "Hybrid"
    assert analysis.location == "San Antonio, TX"
    assert analysis.conflict is False
    assert analysis.evidence[0].frequency == "2 to 3 days per month"


def test_joined_location_metadata_prefers_hybrid_and_keeps_location():
    content = (
        "Job Role: SRE EngineerLocation: Austin TX/South Lake, TX "
        "(Onsite- Hybrid)Employment Type: Full-Time"
    )

    analysis = analyze_work_arrangement(content)

    assert analysis.status == "Hybrid"
    assert analysis.location == "Austin TX/South Lake, TX"
    assert analysis.evidence[0].location_relation == "office_location"


def test_remote_country_metadata_dedupes_country_code_and_name():
    analysis = analyze_work_arrangement("Remote - MX ; Mexico; Remote")

    assert analysis.status == "Remote"
    assert analysis.location == "Mexico"
    assert analysis.evidence[0].location_relation == "remote_eligibility"


def test_remote_support_and_hybrid_engineering_are_not_work_arrangements():
    analysis = analyze_work_arrangement(
        "Provide remote support for network repairs. This is a hybrid engineering and "
        "operations role supporting cloud systems."
    )

    assert analysis.status == ""
    assert analysis.evidence == ()


def test_structured_work_arrangement_overrides_legacy_resolution():
    resolution = resolve_parser_evidence(
        [],
        "Location: remote - Austin,TX\nContract Length: 6-Months Contract to Hire",
    )

    assert resolution.values["remote_status"] == ("Remote",)
    assert resolution.values["location"] == ("Austin, TX",)
    assert resolution.fields["remote_status"].priority == 95


def test_compensation_location_language_is_not_on_site_evidence():
    content = (
        "Your base salary will be determined based on your location, experience, and the pay "
        "of employees in similar positions. Provide remote support for network repairs."
    )

    analysis = analyze_work_arrangement(content)

    assert analysis.status == ""
    assert analysis.evidence == ()


def test_flexible_header_survives_compensation_work_location_language():
    content = (
        "San Diego\nFlexible\nSeptember 04, 2026\n\n"
        "Individual compensation will vary based on qualifications, skill level, "
        "competencies, and work location."
    )

    analysis = analyze_work_arrangement(content)

    assert analysis.status == "Flexible"
    assert analysis.location == "San Diego"
    assert analysis.conflict is False
