from jaw.explicit_work_arrangement import analyze_explicit_work_arrangement
from jaw.parser_resolution import resolve_parser_evidence


def test_compact_hybrid_remote_badge_is_detected():
    analysis = analyze_explicit_work_arrangement(
        "Sr.DevOps Engineer\nHybrid/Remote · Full Time · Experience: 3-4 years"
    )

    assert analysis.status == "Hybrid"
    assert analysis.rule == "compact_hybrid_remote_badge"


def test_remote_title_suffix_is_detected():
    analysis = analyze_explicit_work_arrangement(
        "CrowdStrike\nPrincipal, Disaster Recovery (Remote)\nAbout the Role"
    )

    assert analysis.status == "Remote"
    assert analysis.rule == "title_remote_suffix"


def test_remote_workforce_and_remote_first_are_detected():
    workforce = analyze_explicit_work_arrangement(
        "Fictiv is continuing to expand our remote US workforce."
    )
    remote_first = analyze_explicit_work_arrangement(
        "Discover our Benefits:\nRemote First, Remote Always"
    )

    assert workforce.status == "Remote"
    assert remote_first.status == "Remote"


def test_customer_site_work_location_is_on_site():
    analysis = analyze_explicit_work_arrangement("Work Location: Customer- site")

    assert analysis.status == "On-site"
    assert analysis.rule == "work_location_customer_site"


def test_home_based_is_remote_and_preserves_simple_location():
    analysis = analyze_explicit_work_arrangement("Home-based, Texas")

    assert analysis.status == "Remote"
    assert analysis.location == "Texas"


def test_technical_remote_and_hybrid_phrases_remain_ignored():
    analysis = analyze_explicit_work_arrangement(
        "Provide remote support for hybrid cloud infrastructure and remote monitoring."
    )

    assert analysis.status == ""


def test_explicit_fallback_only_fills_missing_primary_status():
    resolution = resolve_parser_evidence(
        [],
        "Fictiv is continuing to expand our remote US workforce.",
    )

    assert resolution.values["remote_status"] == ("Remote",)
    assert resolution.fields["remote_status"].priority == 96


def test_primary_work_arrangement_still_wins_when_it_resolves():
    resolution = resolve_parser_evidence(
        [],
        "This hybrid role requires three days per week in our Austin, TX office.\n"
        "Remote First, Remote Always",
    )

    assert resolution.values["remote_status"] == ("Hybrid",)
    assert resolution.fields["remote_status"].priority == 95
