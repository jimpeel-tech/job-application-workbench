from jaw.parser_resolution import resolve_parser_evidence


def test_earlier_capture_breaks_otherwise_tied_title_candidates():
    resolution = resolve_parser_evidence(
        [
            {
                "capture_context": "job_description",
                "fields": {"title": "Senior Reliability Engineer"},
            },
            {
                "capture_context": "job_description",
                "fields": {"title": "Staff Site Reliability Engineer"},
            },
        ]
    )

    assert resolution.values["title"] == ("Senior Reliability Engineer",)


def test_title_capture_order_does_not_override_stronger_context():
    resolution = resolve_parser_evidence(
        [
            {
                "capture_context": "job_description",
                "fields": {"title": "Descriptive Engineer Title"},
            },
            {
                "capture_context": "job_title",
                "fields": {"title": "Authoritative Engineer Title"},
            },
        ]
    )

    assert resolution.values["title"] == ("Authoritative Engineer Title",)
