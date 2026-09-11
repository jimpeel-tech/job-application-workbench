from jaw.location_candidate import sanitize_location_candidate
from jaw.parser_resolution import resolve_parser_evidence


def test_location_candidate_cleans_common_ats_artifacts():
    assert sanitize_location_candidate("US- #LI") == "United States"
    assert sanitize_location_candidate("Houston, TX ( if local to Houston") == "Houston, TX"
    assert sanitize_location_candidate("/ (within the US") == "United States"


def test_location_candidate_rejects_non_location_metadata_and_prose():
    assert sanitize_location_candidate("Work Type") == ""
    assert sanitize_location_candidate("Digital Platform Group") == ""
    assert sanitize_location_candidate("100% working") == ""
    assert (
        sanitize_location_candidate(
            "Reporting where work can/needs to be performed / collaboration should happen. "
            "If the person lives w/n 50 miles of such a location, they are expected to come in."
        )
        == ""
    )


def test_clean_location_survives_resolution():
    resolution = resolve_parser_evidence(
        [],
        "LTK Dallas\nStaff Platform Engineer\nUnited States\n"
        "Job title: Staff Software Engineer, Platform\n"
        "Location: US-Remote  #LI-Remote",
    )

    assert resolution.values["location"] == ("United States",)


def test_rejected_workplace_location_allows_explicit_location_fallback():
    resolution = resolve_parser_evidence(
        [],
        "McGraw Hill\nLead Site Reliability Engineer\nUnited States\nTechnology\n"
        "Digital Platform Group\nRemote\n50146\nExempt\n"
        "This is a remote position open to applicants authorized to work for any employer "
        "within the United States.",
    )

    assert resolution.values["location"] == ("United States",)


def test_remote_work_type_heading_does_not_become_location():
    resolution = resolve_parser_evidence(
        [],
        "Netflix\nSite Reliability Engineer 5 - Live SRE\n"
        "Job Requisition ID\nJR39628\nTeams\nEngineering\nWork Type\nRemote",
    )

    assert resolution.values["remote_status"] == ("Remote",)
    assert resolution.values["location"] == ()


def test_remote_policy_prose_does_not_become_location():
    resolution = resolve_parser_evidence(
        [],
        "GM\nPrincipal Site Reliability Engineer\n"
        "Remote: Reporting where work can/needs to be performed / collaboration should happen. "
        "If the person lives w/n 50 miles of such a location, they are expected to come in "
        "three times a week.",
    )

    assert resolution.values["location"] == ()
