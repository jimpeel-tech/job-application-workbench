from jaw.parser_resolution import resolve_parser_evidence
from jaw.work_arrangement import analyze_work_arrangement
from jaw.work_arrangement_guard import suppress_work_arrangement


def test_remote_work_stipend_is_not_a_work_arrangement():
    content = (
        "Our benefits include unlimited PTO, stipends for remote work and wellness, "
        "and a professional development budget."
    )

    analysis = analyze_work_arrangement(content)

    assert analysis.status == "Remote"
    assert suppress_work_arrangement(analysis) is True
    assert resolve_parser_evidence([], content).values["remote_status"] == ()


def test_real_remote_role_is_not_suppressed_by_remote_work_stipend():
    content = (
        "This is a remote role open to candidates in the United States. "
        "Benefits include a stipend for remote work equipment."
    )

    analysis = analyze_work_arrangement(content)

    assert analysis.status == "Remote"
    assert suppress_work_arrangement(analysis) is False
    assert resolve_parser_evidence([], content).values["remote_status"] == ("Remote",)
