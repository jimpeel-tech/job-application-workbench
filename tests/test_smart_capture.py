from __future__ import annotations

from jaw.smart_capture import (
    build_capture_verification_messages,
    capture_tone,
    collect_parser_values,
    default_smart_capture_settings,
    merge_capture_values,
    normalize_smart_capture_settings,
)


def test_smart_capture_settings_preserve_order_visibility_and_modes():
    settings = normalize_smart_capture_settings(
        {
            "field_order": ["title", "company", "pay"],
            "visible_fields": ["title", "pay"],
            "analysis_mode": "ollama",
            "focus_mode": False,
            "dev": True,
        }
    )
    assert settings["field_order"][:3] == ["title", "company", "pay"]
    assert settings["visible_fields"] == ["title", "pay"]
    assert settings["analysis_mode"] == "ollama"
    assert settings["focus_mode"] is False
    assert settings["dev"] is True
    assert set(settings["field_order"]) == set(default_smart_capture_settings()["field_order"])


def test_parser_summary_includes_identity_and_decision_fields():
    text = """Acme Corp
Senior Platform Engineer
Location: Austin, TX
This is a remote role. Full-time. Salary $170,000 - $210,000 annually.
No on-call rotation. Travel up to 10%. Visa sponsorship is available.
"""
    values = collect_parser_values([], text)
    assert values["company"] == ("Acme Corp",)
    assert "Platform Engineer" in values["title"][0]
    assert values["remote_status"]
    assert values["pay"]
    assert values["on_call"] == ("Not required",)
    assert values["travel"] == ("Up to 10%",)
    assert values["sponsorship"] == ("Available",)


def test_ai_merge_tracks_provenance_and_disagreements_without_overwriting_parser():
    parser = {
        "company": ("Acme Corp",),
        "title": ("Platform Engineer",),
        "remote_status": ("Remote",),
        "location": ("Austin, TX",),
    }
    payload = {
        "fields": {
            "company": "Acme Corp",
            "title": "Platform Engineer",
            "pay": "$180,000–$210,000 per year",
            "remote_status": "Hybrid",
            "location": "Austin, TX",
            "employment_type": "",
            "schedule": "",
            "on_call": "",
            "travel": "Up to 20%",
            "clearance": "",
            "sponsorship": "",
            "application_deadline": "",
        },
        "evidence": {
            "company": "Acme Corp",
            "title": "Platform Engineer",
            "pay": "$180,000–$210,000 per year",
            "remote_status": "hybrid schedule",
            "location": "Austin, TX",
            "travel": "travel up to 20%",
        },
        "insights": ["Requires production ownership"],
    }
    settings = normalize_smart_capture_settings({"analysis_mode": "enhanced"})
    merged, insights = merge_capture_values(parser, payload, settings)
    assert merged["company"].source == "both"
    assert merged["company"].review_status == "verified"
    assert merged["pay"].source == "ai"
    assert merged["pay"].review_status == "parser_gap"
    assert merged["remote_status"].source == "conflict"
    assert merged["remote_status"].review_status == "true_conflict"
    assert merged["remote_status"].values == ("Remote", "Hybrid")
    assert merged["remote_status"].evidence == "hybrid schedule"
    assert insights == ("Requires production ownership",)


def test_ollama_only_ignores_parser_values_and_parser_prompt_context():
    parser = {
        "company": ("Parser Corp",),
        "title": ("Parser Engineer",),
        "remote_status": ("Remote",),
    }
    payload = {
        "fields": {
            "company": "Ollama Corp",
            "title": "Platform Engineer",
            "pay": "",
            "remote_status": "Hybrid",
            "location": "",
            "employment_type": "",
            "schedule": "",
            "on_call": "",
            "travel": "",
            "clearance": "",
            "sponsorship": "",
            "application_deadline": "",
        },
        "evidence": {"company": "Ollama Corp", "remote_status": "Hybrid"},
        "insights": [],
    }
    settings = normalize_smart_capture_settings({"analysis_mode": "ollama"})
    merged, insights = merge_capture_values(parser, payload, settings)

    assert merged["company"].values == ("Ollama Corp",)
    assert merged["company"].source == "ai"
    assert merged["remote_status"].values == ("Hybrid",)
    assert merged["remote_status"].conflict is False
    assert insights == ()

    messages = build_capture_verification_messages(
        "Ollama Corp is hiring a Platform Engineer.", parser, "ollama"
    )
    user_prompt = messages[-1]["content"]
    assert "Parser output" not in user_prompt
    assert "Parser Corp" not in user_prompt


def test_capture_highlight_rules_are_preferences_not_extraction_logic():
    settings = default_smart_capture_settings()
    merged, _ = merge_capture_values(
        {
            "remote_status": ("Remote",),
            "on_call": ("Required",),
            "travel": ("Up to 30%",),
        },
        None,
        settings,
    )
    assert capture_tone(merged["remote_status"], settings) == "positive"
    assert capture_tone(merged["on_call"], settings) == "warning"
    assert capture_tone(merged["travel"], settings) == "warning"


def test_semantically_equivalent_pay_is_verified_without_rewriting_parser_value():
    parser_value = "$200000–250000 per year"
    parser = {"pay": (parser_value,)}
    payload = {
        "fields": {
            "company": "",
            "title": "",
            "pay": "$200,000 - $250,000 /yr",
            "remote_status": "",
            "location": "",
            "employment_type": "",
            "schedule": "",
            "on_call": "",
            "travel": "",
            "clearance": "",
            "sponsorship": "",
            "application_deadline": "",
        },
        "evidence": {"pay": "$200,000 - $250,000 /yr"},
        "insights": [],
    }

    merged, _ = merge_capture_values(
        parser,
        payload,
        normalize_smart_capture_settings({"analysis_mode": "verify"}),
    )

    assert merged["pay"].source == "both"
    assert merged["pay"].review_status == "verified"
    assert merged["pay"].conflict is False
    assert merged["pay"].values == (parser_value,)
    assert merged["pay"].evidence == "$200,000 - $250,000 /yr"


def test_meaningfully_different_pay_remains_a_conflict():
    parser = {"pay": ("$200K-$250K annually",)}
    payload = {
        "fields": {
            "company": "",
            "title": "",
            "pay": "$200K-$250K /hr",
            "remote_status": "",
            "location": "",
            "employment_type": "",
            "schedule": "",
            "on_call": "",
            "travel": "",
            "clearance": "",
            "sponsorship": "",
            "application_deadline": "",
        },
        "evidence": {"pay": "$200K-$250K /hr"},
        "insights": [],
    }

    merged, _ = merge_capture_values(
        parser,
        payload,
        normalize_smart_capture_settings({"analysis_mode": "verify"}),
    )

    assert merged["pay"].source == "conflict"
    assert merged["pay"].review_status == "true_conflict"
    assert merged["pay"].conflict is True


def test_ai_echo_without_evidence_is_uncertain_not_verified():
    settings = normalize_smart_capture_settings({"analysis_mode": "verify"})
    merged, _ = merge_capture_values(
        {"company": ("Acme Corp",)},
        {
            "fields": {"company": "Acme Corp"},
            "evidence": {"company": ""},
            "insights": [],
        },
        settings,
    )

    field = merged["company"]
    assert field.values == ("Acme Corp",)
    assert field.source == "parser"
    assert field.review_status == "ai_uncertain"
    assert field.ai_value == "Acme Corp"
    assert field.conflict is False
    assert capture_tone(field, settings) == "warning"


def test_supported_ai_value_without_parser_is_a_parser_gap():
    merged, _ = merge_capture_values(
        {},
        {
            "fields": {"location": "Austin, TX"},
            "evidence": {"location": "Location: Austin, TX"},
            "insights": [],
        },
        normalize_smart_capture_settings({"analysis_mode": "verify"}),
    )

    assert merged["location"].source == "ai"
    assert merged["location"].review_status == "parser_gap"
    assert merged["location"].values == ("Austin, TX",)


def test_unsupported_ai_disagreement_does_not_pollute_parser_values():
    merged, _ = merge_capture_values(
        {"remote_status": ("Remote",)},
        {
            "fields": {"remote_status": "Hybrid"},
            "evidence": {"remote_status": ""},
            "insights": [],
        },
        normalize_smart_capture_settings({"analysis_mode": "verify"}),
    )

    field = merged["remote_status"]
    assert field.values == ("Remote",)
    assert field.source == "parser"
    assert field.review_status == "ai_uncertain"
    assert field.ai_value == "Hybrid"
    assert field.conflict is False
