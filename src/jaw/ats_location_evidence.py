from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AtsLocationEvidence:
    value: str
    relation: str = "posting_location"
    rule: str = "ats_posting_location"


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
_CANADIAN_PROVINCES = {
    "alberta",
    "british columbia",
    "manitoba",
    "new brunswick",
    "newfoundland and labrador",
    "nova scotia",
    "ontario",
    "prince edward island",
    "quebec",
    "saskatchewan",
    "northwest territories",
    "nunavut",
    "yukon",
}
_CITY = r"(?:[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,4})"
_STATE_NAMES = "|".join(
    sorted((re.escape(name) for name in _STATE_NAME_TO_CODE), key=len, reverse=True)
)
_PROVINCES = "|".join(
    sorted((re.escape(name) for name in _CANADIAN_PROVINCES), key=len, reverse=True)
)
_US_FULL = re.compile(
    rf"\b(?P<city>{_CITY}),\s*(?P<region>(?i:{_STATE_NAMES})),\s*"
    r"(?i:United States(?: of America)?)\b"
)
_CANADA_FULL = re.compile(
    rf"\b(?P<city>{_CITY}),\s*(?P<region>(?i:{_PROVINCES})),\s*(?i:Canada)\b"
)
_BODY_MARKER = re.compile(
    r"(?mi)^\s*(?:Job Description|The Opportunity|Our Mission|About the Role|"
    r"About the Team|Job Summary|Responsibilities)\s*$"
)


def analyze_ats_locations(content: str) -> tuple[AtsLocationEvidence, ...]:
    """Extract explicit posting-location metadata, including multi-location ATS headers."""
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return ()

    header = _header_region(text)
    matches: list[tuple[int, AtsLocationEvidence]] = []

    for match in _US_FULL.finditer(header):
        state = _STATE_NAME_TO_CODE[match.group("region").casefold()]
        city = _clean_city(match.group("city"))
        matches.append(
            (
                match.start(),
                AtsLocationEvidence(
                    value=f"{city}, {state}",
                    rule="ats_us_city_state_country",
                ),
            )
        )

    for match in _CANADA_FULL.finditer(header):
        city = _clean_city(match.group("city"))
        province = " ".join(word.capitalize() for word in match.group("region").split())
        matches.append(
            (
                match.start(),
                AtsLocationEvidence(
                    value=f"{city}, {province}, Canada",
                    rule="ats_canada_city_province_country",
                ),
            )
        )

    result: list[AtsLocationEvidence] = []
    seen: set[str] = set()
    for _, item in sorted(matches, key=lambda entry: entry[0]):
        key = item.value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return tuple(result)


def _header_region(text: str) -> str:
    candidate = text[:1800]
    marker = _BODY_MARKER.search(candidate)
    if marker:
        candidate = candidate[: marker.start()]
    return candidate


def _clean_city(value: str) -> str:
    city = " ".join(str(value).split())
    city = re.sub(r"^(?:Job\s+)?Location\s+", "", city)
    return city.strip()


__all__ = ["AtsLocationEvidence", "analyze_ats_locations"]
