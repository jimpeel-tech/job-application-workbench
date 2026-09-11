from jaw.explicit_on_call import analyze_explicit_on_call
from jaw.parser_resolution import resolve_parser_evidence


def test_participates_in_on_call_shifts_is_required():
    evidence = analyze_explicit_on_call(
        "Provides operational support for technology.\n"
        "Participates in on-call shifts to address issues."
    )

    assert evidence.value == "Required"
    assert evidence.rule == "participates_on_call_shifts"


def test_explicit_on_call_shifts_flow_through_parser_resolution():
    resolution = resolve_parser_evidence(
        [],
        "Troubleshooting and Resolution:\n"
        "Participates in on-call shifts to address issues.\n"
        "Resolves technical issues spanning various services.",
    )

    assert resolution.values["on_call"] == ("Required",)
