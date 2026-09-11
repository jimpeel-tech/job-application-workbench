from __future__ import annotations

import re

_STATE_CODES = (
    r"(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|"
    r"MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|"
    r"TX|UT|VT|VA|WA|WV|WI|WY|DC)"
)
_CITY = r"(?:[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,4})"
_CITY_STATE_START = re.compile(
    rf"^\s*(?P<city>{_CITY}),\s*(?P<state>{_STATE_CODES})\b",
    re.IGNORECASE,
)
_US_TEXT = r"(?:US|U\.S\.?|USA|U\.S\.A\.?|United States(?: of America)?)"
_US_ONLY = re.compile(rf"^\s*{_US_TEXT}\s*$", re.IGNORECASE)
_US_WITH_ARRANGEMENT = re.compile(
    rf"^\s*{_US_TEXT}\s*(?:[-/|]\s*)?(?:remote|virtual)?\s*$",
    re.IGNORECASE,
)
_WITHIN_US = re.compile(
    rf"\bwithin\s+(?:the\s+)?{_US_TEXT}\b",
    re.IGNORECASE,
)
# Some upstream location cleanup removes the arrangement suffix from tags such
# as #LI-Remote, leaving a bare trailing #LI. Both forms are tracking metadata,
# not geography.
_LI_TAG = re.compile(
    r"(?:\s*#LI(?:-[A-Za-z0-9_-]+)?)+\s*$",
    re.IGNORECASE,
)


def sanitize_location_candidate(value: str) -> str:
    """Clean or reject a resolved location candidate before it blocks fallbacks.

    This deliberately handles only high-confidence cleanup. It does not convert
    Remote/Home-based/Hybrid into geography and does not attempt fuzzy location
    inference.
    """
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""

    # ATS tracking tags frequently trail a real country token after arrangement
    # words have already been removed by the workplace parser.
    text = _LI_TAG.sub("", text).strip(" \t-–—|•·:;/()")
    if not text:
        return ""

    if _US_ONLY.fullmatch(text) or _US_WITH_ARRANGEMENT.fullmatch(text):
        return "United States"

    if _WITHIN_US.search(text):
        return "United States"

    # Preserve the explicit city/state portion and drop conditional arrangement
    # notes such as "Houston, TX (Remote if local to Houston)".
    city_state = _CITY_STATE_START.match(text)
    if city_state:
        return f"{city_state.group('city')}, {city_state.group('state').upper()}"

    lowered = text.casefold()
    blocked_exact = {
        "work type",
        "100% working",
        "digital platform group",
    }
    if lowered in blocked_exact:
        return ""

    if any(
        marker in lowered
        for marker in (
            "job type:",
            "industry:",
            "experience level:",
            "where work can/needs to be performed",
            "collaboration should happen",
        )
    ):
        return ""

    # Long prose with no recognizable geographic anchor is not a location.
    if len(text.split()) > 12 and not re.search(rf"\b(?:{_STATE_CODES}|{_US_TEXT})\b", text, re.I):
        return ""

    return text


__all__ = ["sanitize_location_candidate"]
