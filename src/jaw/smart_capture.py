from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from .parser_resolution import resolve_parser_values
from .value_canonicalization import canonical_capture_value

SMART_CAPTURE_FIELD_DEFINITIONS = (
    ("company", "Company"),
    ("title", "Title"),
    ("pay", "Pay"),
    ("remote_status", "Work arrangement"),
    ("location", "Location"),
    ("employment_type", "Employment"),
    ("schedule", "Schedule"),
    ("on_call", "On-call"),
    ("travel", "Travel"),
    ("clearance", "Clearance"),
    ("sponsorship", "Sponsorship"),
    ("application_deadline", "Deadline"),
)
SMART_CAPTURE_FIELD_KEYS = tuple(key for key, _label in SMART_CAPTURE_FIELD_DEFINITIONS)
SMART_CAPTURE_FIELD_LABELS = dict(SMART_CAPTURE_FIELD_DEFINITIONS)

DEFAULT_OLLAMA_CAPTURE_MODEL = "qwen3:14b"

_DEFAULT_SETTINGS: dict[str, Any] = {
    "field_order": list(SMART_CAPTURE_FIELD_KEYS),
    "visible_fields": list(SMART_CAPTURE_FIELD_KEYS),
    "show_empty_fields": False,
    "focus_mode": False,
    "analysis_mode": "verify",
    "ollama_model": DEFAULT_OLLAMA_CAPTURE_MODEL,
    "fill_missing": True,
    "report_disagreements": True,
    "warn_non_remote": True,
    "warn_on_call": True,
    "warn_travel": True,
    "warn_sponsorship": True,
    "dev": False,
}

CAPTURE_VERIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fields": {
            "type": "object",
            "properties": {key: {"type": "string"} for key in SMART_CAPTURE_FIELD_KEYS},
            "required": list(SMART_CAPTURE_FIELD_KEYS),
            "additionalProperties": False,
        },
        "evidence": {
            "type": "object",
            "properties": {key: {"type": "string"} for key in SMART_CAPTURE_FIELD_KEYS},
            "required": list(SMART_CAPTURE_FIELD_KEYS),
            "additionalProperties": False,
        },
        "insights": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 8,
        },
    },
    "required": ["fields", "evidence", "insights"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class CaptureDisplayField:
    key: str
    label: str
    values: tuple[str, ...] = ()
    source: str = "none"
    confidence: float = 0.0
    evidence: str = ""
    conflict: bool = False
    review_status: str = "none"
    ai_value: str = ""

    @property
    def display_value(self) -> str:
        return "  |  ".join(self.values)


def default_smart_capture_settings() -> dict[str, Any]:
    return {
        key: list(value) if isinstance(value, list) else value
        for key, value in _DEFAULT_SETTINGS.items()
    }


def normalize_smart_capture_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    incoming = dict(raw or {})
    settings = default_smart_capture_settings()

    incoming_order = [
        str(value)
        for value in incoming.get("field_order", [])
        if str(value) in SMART_CAPTURE_FIELD_KEYS
    ]
    seen: set[str] = set()
    order: list[str] = []
    for key in [*incoming_order, *SMART_CAPTURE_FIELD_KEYS]:
        if key not in seen:
            seen.add(key)
            order.append(key)
    settings["field_order"] = order

    if "visible_fields" in incoming:
        settings["visible_fields"] = [
            key
            for key in order
            if key
            in {
                str(value)
                for value in incoming.get("visible_fields", [])
                if str(value) in SMART_CAPTURE_FIELD_KEYS
            }
        ]

    mode = str(incoming.get("analysis_mode", settings["analysis_mode"])).strip().lower()
    settings["analysis_mode"] = (
        mode if mode in {"parser", "verify", "ollama", "enhanced"} else "verify"
    )

    model = str(incoming.get("ollama_model", settings["ollama_model"])).strip()
    settings["ollama_model"] = model or DEFAULT_OLLAMA_CAPTURE_MODEL

    for key in (
        "show_empty_fields",
        "focus_mode",
        "fill_missing",
        "report_disagreements",
        "warn_non_remote",
        "warn_on_call",
        "warn_travel",
        "warn_sponsorship",
        "dev",
    ):
        if key in incoming:
            settings[key] = bool(incoming[key])

    return settings


def combine_capture_text(events: Iterable[dict[str, Any]]) -> str:
    return "\n\n".join(
        str(event.get("content", "")).strip()
        for event in events
        if str(event.get("content", "")).strip()
    )


def collect_parser_values(
    extractions: Iterable[dict[str, Any]],
    combined_text: str = "",
) -> dict[str, tuple[str, ...]]:
    return resolve_parser_values(extractions, combined_text)


def merge_capture_values(
    parser_values: dict[str, tuple[str, ...]],
    ai_payload: dict[str, Any] | None,
    settings: dict[str, Any],
) -> tuple[dict[str, CaptureDisplayField], tuple[str, ...]]:
    settings = normalize_smart_capture_settings(settings)
    ai_payload = dict(ai_payload or {})
    ai_fields = dict(ai_payload.get("fields", {}))
    evidence = dict(ai_payload.get("evidence", {}))
    mode = str(settings["analysis_mode"])

    merged: dict[str, CaptureDisplayField] = {}
    for key in SMART_CAPTURE_FIELD_KEYS:
        parser = tuple(
            str(value).strip() for value in parser_values.get(key, ()) if str(value).strip()
        )
        ai_value = str(ai_fields.get(key, "")).strip() if mode != "parser" else ""
        ai_evidence = str(evidence.get(key, "")).strip()

        if mode == "ollama":
            status = "ai_only" if ai_value and ai_evidence else "ai_uncertain" if ai_value else "empty"
            merged[key] = CaptureDisplayField(
                key=key,
                label=SMART_CAPTURE_FIELD_LABELS[key],
                values=(ai_value,) if ai_value else (),
                source="ai" if ai_value else "none",
                confidence=(0.8 if ai_evidence else 0.5) if ai_value else 0.0,
                evidence=ai_evidence,
                conflict=False,
                review_status=status,
                ai_value=ai_value,
            )
            continue

        parser_normalized = {
            canonical_capture_value(key, value) for value in parser
        }
        ai_normalized = canonical_capture_value(key, ai_value)

        source = "parser" if parser else "none"
        values = parser
        conflict = len(parser) > 1
        confidence = 0.6 if conflict else 1.0 if parser else 0.0
        review_status = "parser_conflict" if conflict else "parser_only" if parser else "empty"

        if ai_value:
            if ai_normalized in parser_normalized:
                if ai_evidence:
                    source = "both"
                    confidence = 0.95 if len(parser) == 1 else 0.7
                    if len(parser) == 1:
                        conflict = False
                        review_status = "verified"
                elif len(parser) == 1:
                    source = "parser"
                    confidence = 0.8
                    conflict = False
                    review_status = "ai_uncertain"
            elif parser:
                if ai_evidence:
                    review_status = "true_conflict"
                    confidence = 0.5
                    if settings["report_disagreements"]:
                        values = (*parser, ai_value)
                        source = "conflict"
                        conflict = True
                    else:
                        source = "parser"
                        conflict = len(parser) > 1
                else:
                    review_status = "ai_uncertain"
                    confidence = 0.65
                    source = "parser"
                    conflict = len(parser) > 1
            else:
                review_status = "parser_gap" if ai_evidence else "ai_uncertain"
                confidence = 0.75 if ai_evidence else 0.4
                if settings["fill_missing"] or mode == "enhanced":
                    values = (ai_value,)
                    source = "ai"

        merged[key] = CaptureDisplayField(
            key=key,
            label=SMART_CAPTURE_FIELD_LABELS[key],
            values=values,
            source=source,
            confidence=confidence,
            evidence=ai_evidence,
            conflict=conflict,
            review_status=review_status,
            ai_value=ai_value,
        )

    insights = tuple(
        str(value).strip()
        for value in ai_payload.get("insights", [])
        if mode == "enhanced" and str(value).strip()
    )
    return merged, insights


def capture_tone(
    field: CaptureDisplayField,
    settings: dict[str, Any],
) -> str:
    settings = normalize_smart_capture_settings(settings)
    value = field.display_value.casefold()
    if field.conflict or field.review_status in {"true_conflict", "ai_uncertain", "parser_conflict"}:
        return "warning"
    if field.key == "remote_status":
        if (
            "remote" in value
            and "hybrid" not in value
            and "on-site" not in value
            and "onsite" not in value
        ):
            return "positive"
        if settings["warn_non_remote"] and any(
            token in value for token in ("hybrid", "on-site", "onsite", "office")
        ):
            return "warning"
    if (
        field.key == "on_call"
        and settings["warn_on_call"]
        and "required" in value
        and "not required" not in value
    ):
        return "warning"
    if field.key == "travel" and settings["warn_travel"]:
        percentages = [int(match) for match in re.findall(r"(\d{1,3})\s*%", value)]
        if percentages and max(percentages) >= 25:
            return "warning"
    if (
        field.key == "sponsorship"
        and settings["warn_sponsorship"]
        and any(token in value for token in ("not offered", "not available", "no sponsorship"))
    ):
        return "warning"
    return "normal"


def build_capture_verification_messages(
    description: str,
    parser_values: dict[str, tuple[str, ...]],
    mode: str,
) -> list[dict[str, str]]:
    mode = str(mode).strip().lower()
    parser_summary = {key: " | ".join(values) for key, values in parser_values.items() if values}

    if mode == "ollama":
        task = (
            "Extract every supported field directly from the posting. Do not use or "
            "assume any parser output. Return empty strings when the posting does not "
            "explicitly support a field."
        )
        user_content = f"{task}\n\nJob posting:\n{description}"
    elif mode == "verify":
        task = (
            "Verify the parser output and fill only fields that are missing or clearly "
            "contradicted by explicit text."
        )
        user_content = (
            f"{task}\n\n"
            f"Parser output:\n{json.dumps(parser_summary, ensure_ascii=False, indent=2)}\n\n"
            f"Job posting:\n{description}"
        )
    else:
        task = (
            "Extract all supported fields and add a few concise decision-relevant "
            "insights that do not fit the fixed fields."
        )
        user_content = (
            f"{task}\n\n"
            f"Parser output:\n{json.dumps(parser_summary, ensure_ascii=False, indent=2)}\n\n"
            f"Job posting:\n{description}"
        )

    return [
        {
            "role": "system",
            "content": (
                "You extract and verify job-posting facts for a local desktop tool. "
                "Use only explicit evidence from the supplied posting. Never infer or "
                "guess. Return empty strings for unsupported fields. Evidence must be a "
                "short verbatim-or-near-verbatim phrase from the posting. Do not score "
                "the candidate and do not write to any database."
            ),
        },
        {"role": "user", "content": user_content},
    ]
