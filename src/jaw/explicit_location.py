from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExplicitLocation:
    value: str = ""
    rule: str = ""


_STATE_NAME_TO_CODE = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "district of columbia": "DC",
}
_STATE_CODES = (
    r"(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|"
    r"MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|"
    r"TX|UT|VT|VA|WA|WV|WI|WY|DC)"
)
_STATE_NAMES = "|".join(
    sorted((re.escape(name) for name in _STATE_NAME_TO_CODE), key=len, reverse=True)
)
_CITY = r"(?:[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,4})"
_CITY_STATE_CODE = re.compile(rf"\b(?P<city>{_CITY}),\s*(?P<state>{_STATE_CODES})\b")
_CITY_STATE_NAME = re.compile(
    rf"\b(?P<city>{_CITY}),\s*(?P<state>{_STATE_NAMES})\b",
    re.IGNORECASE,
)
_US = re.compile(
    r"\b(?:United States(?: of America)?|U\.?S\.?A?\.?)\b",
    re.IGNORECASE,
)
_LOCATION_HEADER = re.compile(
    r"^(?:job\s+)?location(?:\s*&\s*workplace)?$|^job\s+type\s*&\s*location$",
    re.IGNORECASE,
)


def analyze_explicit_location(content: str) -> ExplicitLocation:
    """Extract high-confidence geography without treating work arrangement as location."""
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return ExplicitLocation()

    lines = [" ".join(line.split()).strip() for line in text.splitlines() if line.strip()]

    # Labeled location sections are authoritative even when the value is written
    # as a short sentence rather than a bare city/state string.
    for index, line in enumerate(lines[:-1]):
        if not _LOCATION_HEADER.fullmatch(line):
            continue
        value = _location_from_role_line(lines[index + 1])
        if value:
            return ExplicitLocation(value, "location_header")

    # Many ATS exports put a bare location or street address directly below the
    # company/title block. Keep this deliberately limited to the first few lines
    # and require the entire line to look metadata-like.
    for line in lines[:10]:
        value = _metadata_location(line)
        if value:
            return ExplicitLocation(value, "top_location_metadata")

    role_patterns = (
        re.compile(
            rf"\b(?:position|role|job)\b[^.\n]{{0,70}}\b(?:based\s+out\s+of|based\s+in|"
            rf"located\s+in|located\s+at|on[- ]?site\s+(?:role\s+)?at)\s+"
            rf"(?P<location>[^.;\n]{{2,100}})",
            re.IGNORECASE,
        ),
        re.compile(
            rf"\bbased\s+full[- ]time\s+in\s+(?P<location>[^.;\n]{{2,80}})",
            re.IGNORECASE,
        ),
        re.compile(
            rf"\bremote\s+work\s+in\s+(?P<location>[^.;\n]{{2,80}}?)(?:\s+only\b|[.;\n])",
            re.IGNORECASE,
        ),
    )
    for pattern in role_patterns:
        for match in pattern.finditer(text):
            value = _normalize_location_phrase(match.group("location"))
            if value:
                return ExplicitLocation(value, "role_location_prose")

    # Office attendance can name a city without its state. Infer the state only
    # when the same city appears elsewhere with an explicit state name/code.
    office_city = re.search(
        rf"\b(?:on[- ]?site|in[- ]office)\b[^.\n]{{0,40}}\b(?:at|in)\s+"
        rf"(?:the\s+)?(?P<city>{_CITY})\s+office\b",
        text,
        re.IGNORECASE,
    )
    if office_city:
        value = _infer_city(office_city.group("city"), text)
        if value:
            return ExplicitLocation(value, "office_city_with_inferred_state")

    # Remote geography is still geography: preserve the country while leaving the
    # Remote/Hybrid/On-site classification to the work-arrangement analyzers.
    country_patterns = (
        r"\bremote\s+(?:role|position|job)\b[^.\n]{0,80}\bbased\s+in\s+(?:the\s+)?(?P<country>U\.?S\.?A?\.?|United States(?: of America)?)\b",
        r"\b(?:role|position|job|candidate|employee)s?\b[^.\n]{0,90}\b(?:within|in|throughout|based\s+in)\s+(?:the\s+)?(?P<country>U\.?S\.?A?\.?|United States(?: of America)?)\b",
    )
    for pattern in country_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return ExplicitLocation("United States", "explicit_us_scope")

    return ExplicitLocation()


def _metadata_location(line: str) -> str:
    text = " ".join(str(line).split()).strip(" ,")
    if not text or len(text) > 120 or any(mark in text for mark in (":", "$", "•", "|")):
        return ""
    if text.endswith((".", "!", "?")):
        return ""

    # Exact city/state lines, optionally followed by a country code.
    code = _CITY_STATE_CODE.fullmatch(re.sub(r",\s*(?:US|USA|United States)\s*$", "", text, flags=re.I))
    if code:
        return f"{code.group('city')}, {code.group('state').upper()}"

    named = _CITY_STATE_NAME.fullmatch(text)
    if named:
        return _city_state(named.group("city"), named.group("state"))

    # Street-address metadata: use the trailing city/state component only.
    code_matches = list(_CITY_STATE_CODE.finditer(text))
    if code_matches:
        match = code_matches[-1]
        if match.end() == len(text):
            return f"{match.group('city')}, {match.group('state').upper()}"
    named_matches = list(_CITY_STATE_NAME.finditer(text))
    if named_matches:
        match = named_matches[-1]
        if match.end() == len(text):
            return _city_state(match.group("city"), match.group("state"))

    return ""


def _location_from_role_line(line: str) -> str:
    text = " ".join(str(line).split()).strip()
    role_location = re.search(
        r"\b(?:role|position|job)\b[^.;]{0,45}\b"
        r"(?:based\s+out\s+of|based\s+in|located\s+in|located\s+at|at)\s+"
        r"(?P<location>[^.;]{2,100})",
        text,
        re.IGNORECASE,
    )
    if role_location:
        value = _normalize_location_phrase(role_location.group("location"))
        if value:
            return value

    value = _normalize_location_phrase(text)
    if value:
        return value
    return "United States" if _US.search(text) else ""


def _normalize_location_phrase(value: str) -> str:
    text = " ".join(str(value).split()).strip(" ,()")
    text = re.split(
        r"\b(?:where|while|and\s+the|with\s+the|depending\s+on)\b",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" ,()")
    if not text:
        return ""
    if re.fullmatch(r"NYC", text, re.IGNORECASE):
        return "New York City, NY"

    code = _CITY_STATE_CODE.search(text)
    if code:
        return f"{code.group('city')}, {code.group('state').upper()}"
    named = _CITY_STATE_NAME.search(text)
    if named:
        state = " ".join(word.capitalize() for word in named.group("state").split())
        return f"{named.group('city')}, {state}"
    if re.search(r"\bNew York City\b", text, re.IGNORECASE):
        return "New York City, NY"
    if _US.search(text):
        return "United States"
    return ""


def _infer_city(city: str, text: str) -> str:
    city = " ".join(city.split()).strip(" ,")
    if not city:
        return ""
    if city.casefold() == "nyc":
        return "New York City, NY"

    code = re.search(
        rf"\b{re.escape(city)},\s*(?P<state>{_STATE_CODES})\b",
        text,
        re.IGNORECASE,
    )
    if code:
        return f"{city}, {code.group('state').upper()}"
    named = re.search(
        rf"\b{re.escape(city)},\s*(?P<state>{_STATE_NAMES})\b",
        text,
        re.IGNORECASE,
    )
    if named:
        return _city_state(city, named.group("state"))
    return ""


def _city_state(city: str, state: str) -> str:
    code = _STATE_NAME_TO_CODE.get(str(state).casefold())
    return f"{' '.join(str(city).split())}, {code}" if code else ""


__all__ = ["ExplicitLocation", "analyze_explicit_location"]
