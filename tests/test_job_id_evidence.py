from jaw.job_id_evidence import analyze_job_id
from jaw.parser_resolution import resolve_parser_evidence


def test_job_code_label_is_job_id():
    evidence = analyze_job_id("Job Title: Lead Engineer\nJob Code: 37602\nJob Location: Remote")

    assert evidence.value == "37602"
    assert evidence.rule == "explicit_job_id_label"


def test_ref_code_label_is_job_id():
    evidence = analyze_job_id("Ref. code: 431574\nPosted on: May 10, 2026")

    assert evidence.value == "431574"


def test_inline_title_id_is_job_id():
    evidence = analyze_job_id(
        "Kubernetes & Database Migration Engineer- Remote EST hours - ID:44322"
    )

    assert evidence.value == "44322"
    assert evidence.rule == "inline_job_id"


def test_repeated_standalone_numeric_value_is_job_id():
    evidence = analyze_job_id(
        "Lead Site Reliability Engineer\nRemote\n50146\nExempt\nAbout the role\n50146\nFooter"
    )

    assert evidence.value == "50146"
    assert evidence.rule == "repeated_standalone_job_id"


def test_single_standalone_number_and_repeated_year_are_not_job_ids():
    single = analyze_job_id("Platform Engineer\n50146\nRemote")
    year = analyze_job_id("Posted in 2026\n2026\nUpdated\n2026")

    assert single.value == ""
    assert year.value == ""


def test_explicit_job_id_evidence_flows_through_parser_resolution():
    resolution = resolve_parser_evidence(
        [],
        "Cloud Migration Architect\nRef. code: 431574\nContract Type: Permanent",
    )

    assert resolution.values["job_id"] == ("431574",)
    assert resolution.fields["job_id"].priority == 105
