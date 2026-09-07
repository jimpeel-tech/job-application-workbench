from __future__ import annotations

import json

from jaw.application import CaptureService
from jaw.capture_context import (
    capture_metrics,
    classify_capture_context,
    normalize_capture_for_parser,
)
from jaw.database import JobDatabase
from jaw.parser_resolution import resolve_parser_evidence, resolve_parser_values


def test_collapsed_badge_strip_is_metadata_and_normalizes_known_boundaries():
    raw = "Full-TimeRemote$200,000 - $250,000 /yr"

    classification = classify_capture_context(raw, "job_capture")
    normalized = normalize_capture_for_parser(raw, classification.content_type)
    metrics = capture_metrics(raw, sequence=2)

    assert classification.content_type == "job_metadata"
    assert normalized == "Full-Time\nRemote\n$200,000 - $250,000 /yr"
    assert metrics["sequence"] == 2
    assert metrics["single_line"] is True
    assert metrics["metadata_signals"] >= 2


def test_section_captures_get_specific_contexts_without_forcing_full_description():
    requirements = classify_capture_context(
        "Requirements\n5+ years of Kubernetes experience.\nStrong Linux skills.",
        "job_capture",
    )
    responsibilities = classify_capture_context(
        "Responsibilities\nOperate production Kubernetes clusters.\nOwn incident response.",
        "job_capture",
    )

    assert requirements.content_type == "requirements"
    assert responsibilities.content_type == "responsibilities"


def test_capture_service_preserves_raw_and_stores_parser_normalization(tmp_path):
    database = JobDatabase(tmp_path / "jaw.db")
    service = CaptureService(database)
    raw = "Full-TimeRemote$200,000 - $250,000 /yr"

    accepted = service.accept_text(7, raw)

    event = accepted.session["events"][-1]
    metadata = json.loads(event["metadata"])
    assert event["content"] == raw
    assert event["content_type"] == "job_metadata"
    assert metadata["normalized_content"] == ("Full-Time\nRemote\n$200,000 - $250,000 /yr")
    assert metadata["extraction"]["capture_context"] == "job_metadata"
    assert metadata["metrics"]["sequence"] == 1


def test_explicit_title_capture_outranks_title_inferred_from_long_description():
    values = resolve_parser_values(
        [
            {
                "capture_context": "job_description",
                "fields": {"title": "Software Engineer"},
            },
            {
                "capture_context": "job_title",
                "fields": {"title": "Senior Platform Engineer"},
            },
        ],
        "Software Engineer\nLong description text",
    )

    assert values["title"] == ("Senior Platform Engineer",)


def test_metadata_capture_outranks_description_for_pay_components():
    values = resolve_parser_values(
        [
            {
                "capture_context": "job_description",
                "fields": {
                    "pay_min": "150000",
                    "pay_max": "180000",
                    "currency": "USD",
                    "pay_period": "year",
                },
            },
            {
                "capture_context": "job_metadata",
                "fields": {
                    "pay_min": "200000",
                    "pay_max": "250000",
                    "currency": "USD",
                    "pay_period": "year",
                },
            },
        ]
    )

    assert values["pay"] == ("$200000–250000 per year",)


def test_application_phase_recognizes_common_form_prompt_without_question_mark():
    result = classify_capture_context(
        "Years of experience with Kubernetes",
        "application",
    )
    assert result.content_type == "application_question"


def test_repeated_lower_priority_values_do_not_override_explicit_title_capture():
    resolution = resolve_parser_evidence(
        [
            {"capture_context": "job_title", "fields": {"title": "Senior Platform Engineer"}},
            {"capture_context": "job_description", "fields": {"title": "Software Engineer"}},
            {"capture_context": "job_description", "fields": {"title": "Software Engineer"}},
            {"capture_context": "job_description", "fields": {"title": "Software Engineer"}},
        ]
    )

    assert resolution.values["title"] == ("Senior Platform Engineer",)
    evidence = resolution.fields["title"]
    assert evidence.priority == 100
    assert evidence.support_count == 1
    assert evidence.corroborated is False
    assert evidence.candidates[0].selected is True
    assert any(candidate.value == "Software Engineer" for candidate in evidence.candidates)


def test_independent_corroboration_breaks_equal_priority_tie():
    resolution = resolve_parser_evidence(
        [
            {"capture_context": "job_description", "fields": {"location": "Austin, TX"}},
            {"capture_context": "job_description", "fields": {"location": "Remote, US"}},
            {"capture_context": "job_description", "fields": {"location": "Austin, TX"}},
        ]
    )

    assert resolution.values["location"] == ("Austin, TX",)
    evidence = resolution.fields["location"]
    assert evidence.support_count == 2
    assert evidence.corroborated is True
    assert evidence.contexts == ("job_description",)
    selected = [candidate for candidate in evidence.candidates if candidate.selected]
    assert [candidate.value for candidate in selected] == ["Austin, TX"]


def test_combined_parser_fallback_does_not_count_as_independent_support():
    resolution = resolve_parser_evidence(
        [{"capture_context": "job_description", "fields": {"remote_status": "Remote"}}],
        "This is a remote role.",
    )

    assert resolution.values["remote_status"] == ("Remote",)
    assert resolution.fields["remote_status"].support_count == 1
    assert resolution.fields["remote_status"].corroborated is False
