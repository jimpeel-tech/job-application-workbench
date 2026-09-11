from jaw.explicit_work_arrangement import analyze_explicit_work_arrangement
from jaw.parser_resolution import resolve_parser_evidence
from jaw.work_arrangement import analyze_work_arrangement
from jaw.work_arrangement_guard import suppress_work_arrangement


def test_remote_or_hybrid_option_is_preserved():
    analysis = analyze_explicit_work_arrangement(
        "Location - We are flexible on remote working from home, if you are located in the USA. "
        "We have physical offices in Austin, TX and Tampa, FL, if you prefer a hybrid option."
    )

    assert analysis.status == "Remote or hybrid"
    assert analysis.rule == "remote_or_hybrid_option"


def test_live_and_work_anywhere_in_us_implies_remote():
    analysis = analyze_explicit_work_arrangement(
        "HQ is in Carlsbad, CA. Employee may live and work anywhere in the U.S."
    )

    assert analysis.status == "Remote"
    assert analysis.rule == "live_and_work_anywhere_us"


def test_title_remote_est_hours_suffix_is_detected():
    analysis = analyze_explicit_work_arrangement(
        "Kubernetes & Database Migration Engineer- Remote EST hours - ID:44322"
    )

    assert analysis.status == "Remote"
    assert analysis.rule == "title_remote_schedule_suffix"


def test_hybrid_working_environment_for_all_employees_is_fallback_evidence():
    analysis = analyze_explicit_work_arrangement(
        "At NetApp, we embrace a hybrid working environment designed to strengthen "
        "connection, collaboration, and culture for all employees."
    )

    assert analysis.status == "Hybrid"
    assert analysis.rule == "hybrid_working_environment_policy"


def test_joined_us_remote_posted_header_is_detected():
    analysis = analyze_explicit_work_arrangement(
        "US-RemotePosted Date4 weeks ago(7/2/2026 2:04 PM)"
    )

    assert analysis.status == "Remote"
    assert analysis.rule == "joined_us_remote_header"


def test_onsite_interview_only_is_not_job_work_arrangement():
    text = (
        "This role does require an onsite interview during the process at our "
        "headquarters in Austin, TX - No exceptions"
    )
    analysis = analyze_work_arrangement(text)

    assert analysis.status == "On-site"
    assert suppress_work_arrangement(analysis) is True
    assert resolve_parser_evidence([], text).values["remote_status"] == ()


def test_real_onsite_job_is_not_suppressed_by_interview_guard():
    text = "This is an on-site role at our Austin, TX office."
    analysis = analyze_work_arrangement(text)

    assert analysis.status == "On-site"
    assert suppress_work_arrangement(analysis) is False
