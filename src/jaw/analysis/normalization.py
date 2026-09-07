"""Normalization at the analysis boundary."""

from __future__ import annotations

from typing import Any


def dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def normalize_remote_status(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if not text:
        return "Unclear"
    if text == "remote" or "fully remote" in text:
        return "Remote"
    if "hybrid" in text or "telework" in text:
        return "Hybrid"
    if (
        text == "on-site"
        or text == "onsite"
        or "in-person" in text
        or "not remote" in text
        or "field-based" in text
    ):
        return "On-site"
    return "Unclear"


def normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return exactly the shape the current jobs table/dashboard consumes."""
    pay_min = number(result.get("pay_min"))
    pay_max = number(result.get("pay_max"))
    if pay_min is not None and pay_max is not None and pay_min > pay_max:
        pay_min, pay_max = pay_max, pay_min

    try:
        score = int(result.get("match_score", 0))
    except (TypeError, ValueError):
        score = 0

    return {
        "company": str(result.get("company", "")).strip(),
        "title": str(result.get("title", "")).strip(),
        "location": str(result.get("location", "")).strip(),
        "remote_status": normalize_remote_status(result.get("remote_status")),
        "pay_min": pay_min,
        "pay_max": pay_max,
        "currency": str(result.get("currency", "")).strip(),
        "pay_period": str(result.get("pay_period", "")).strip(),
        "pay_disclosed": bool(
            result.get("pay_disclosed", False)
            or pay_min is not None
            or pay_max is not None
        ),
        "match_score": min(100, max(0, score)),
        "summary": str(result.get("summary", "")).strip(),
        "strong_matches": dedupe_strings(
            [str(value) for value in result.get("strong_matches", [])]
        ),
        "concerns": dedupe_strings(
            [str(value) for value in result.get("concerns", [])]
        ),
        "missing_qualifications": dedupe_strings(
            [str(value) for value in result.get("missing_qualifications", [])]
        ),
    }
