from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_ARRANGEMENT_LABELS = {
    "remote": "Remote",
    "hybrid": "Hybrid",
    "on-site": "On-site",
    "telework": "Telework eligible",
    "field-based": "Field-based",
    "flexible": "Flexible",
}

_ARRANGEMENT_TERM = (
    r"(?:fully\s+remote|remote|hybrid|on[- ]?site|onsite|in[- ]office|"
    r"in[- ]person|telework|field[- ]based|flexible)"
)
_ARRANGEMENT_TOKEN = re.compile(rf"\b{_ARRANGEMENT_TERM}\b", re.IGNORECASE)
_METADATA_LINE = re.compile(
    rf"^\s*(?P<term>{_ARRANGEMENT_TERM})"
    r"(?:\s*(?:[-–—|•·:])\s*(?P<tail>.+?))?\s*$",
    re.IGNORECASE,
)
_LOCATION_ROW = re.compile(
    r"^\s*(?:work\s+)?location\s*:\s*(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_JOINED_LOCATION_ROW = re.compile(
    r"(?:\blocation|(?<=[a-z])(?-i:Location))\s*:\s*(?P<body>.{1,180}?)"
    r"(?=\b(?:Employment\s+Type|Compensation|Contract\s+Length|Benefits|Job\s+Summary)\s*:|$)",
    re.IGNORECASE | re.DOTALL,
)
_REMOTE_TECHNICAL = re.compile(
    r"\bremote\s+(?:access|desktop|sensing|control|monitoring|procedure|repository|"
    r"server|shell|command|connection|endpoint|debugging|support|repair|repairs)\b",
    re.IGNORECASE,
)
_HYBRID_TECHNICAL = re.compile(
    r"\bhybrid\s+(?:cloud|infrastructure|environment|architecture|network|deployment|"
    r"system|systems|platform|engineering|operations|technical)\b",
    re.IGNORECASE,
)
_ATTENDANCE = re.compile(
    r"\b(?:must|required|expected|need(?:ed)?|will|should)\b"
    r"[^.\n]{0,80}\b(?:report|commute|work|be)\b"
    r"[^.\n]{0,90}\b(?:office|on[- ]?site|onsite|in[- ]office|site)\b",
    re.IGNORECASE,
)
_PERIODIC_OFFICE = re.compile(
    r"(?P<clause>[^.\n]{0,100}\b(?:require(?:s|d)?|expected|must|will)\b"
    r"[^.\n]{0,180}(?P<frequency>(?:one|two|three|four|five|\d+)"
    r"(?:\s*(?:-|–|to)\s*(?:one|two|three|four|five|\d+))?\s+days?\s+"
    r"(?:per|a|each)\s+(?:week|month))[^.\n]{0,150}\boffice\b[^.\n]{0,120})",
    re.IGNORECASE,
)
_NOT_REMOTE = re.compile(
    r"\b(?:not|isn't|is not|cannot be|can't be)\s+(?:a\s+)?remote\b|"
    r"\bremote\s+(?:work|option|arrangement)\s+(?:is\s+)?not\s+"
    r"(?:available|offered|permitted)\b",
    re.IGNORECASE,
)
_FEDERAL_REMOTE_NO = re.compile(
    r"\b(?:Remote job|Virtual/Remote)\s*:?[ \t]*(?:\n\s*)?"
    r"(?:No|This is not (?:a )?(?:virtual|remote))\b",
    re.IGNORECASE,
)
_TELEWORK_YES = re.compile(
    r"\bTelework eligible\s*:?[ \t]*(?:\n\s*)?Yes(?P<detail>[^\n.]*)",
    re.IGNORECASE,
)
_FREQUENCY = re.compile(
    r"\b(?:at least\s+)?(?:one|two|three|four|five|\d+)"
    r"(?:\s*(?:-|–|to)\s*(?:one|two|three|four|five|\d+))?\s+days?\s+"
    r"(?:per|a|each)\s+(?:week|month)\b|"
    r"\b(?:once|twice|three times|four times|five times)\s+"
    r"(?:per\s+(?:week|month)|weekly|monthly)\b",
    re.IGNORECASE,
)

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
_CITY_NAME = r"(?:[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,4})"
_CITY_STATE = re.compile(rf"\b({_CITY_NAME},\s*{_STATE_CODES})\b")
_CITY_ONLY = re.compile(rf"\b({_CITY_NAME})\b")
_US_STATE_NAME = re.compile(
    r"\b(?:" + "|".join(re.escape(name) for name in _STATE_NAME_TO_CODE) + r")\b",
    re.IGNORECASE,
)
_US_STATE_CODE = re.compile(rf"\b{_STATE_CODES}\b")
_US_COUNTRY = re.compile(
    r"\b(?:United States(?: of America)?|U\.?S\.?A?\.?)\b",
    re.IGNORECASE,
)
_RESIDENCE = re.compile(
    r"\b(?:must\s+(?:live|reside|be located)|residing|candidates?\s+(?:must\s+be\s+)?"
    r"(?:located|based)|employees?\s+(?:must\s+be\s+)?(?:located|based))\s+"
    r"(?:in|near)\s+(?P<location>[^.;\n]{2,120})",
    re.IGNORECASE,
)
_REMOTE_SCOPE = re.compile(
    r"\bremote(?:ly)?\s+(?:anywhere\s+)?(?:in|within|throughout)\s+"
    r"(?P<location>[^.;\n]{2,120})",
    re.IGNORECASE,
)
_MONTH_DATE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},\s+\d{4}\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WorkArrangementEvidence:
    arrangement: str
    value: str
    evidence: str
    location: str = ""
    location_relation: str = "unknown"
    frequency: str = ""
    confidence: float = 0.0
    rule: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "arrangement": self.arrangement,
            "value": self.value,
            "evidence": self.evidence,
            "location": self.location,
            "location_relation": self.location_relation,
            "frequency": self.frequency,
            "confidence": self.confidence,
            "rule": self.rule,
        }


@dataclass(frozen=True)
class WorkArrangementAnalysis:
    status: str = ""
    location: str = ""
    evidence: tuple[WorkArrangementEvidence, ...] = ()
    conflict: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "location": self.location,
            "conflict": self.conflict,
            "evidence": [item.as_dict() for item in self.evidence],
        }


def analyze_work_arrangement(content: str) -> WorkArrangementAnalysis:
    """Extract role-specific workplace evidence without collapsing geography too early."""
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return WorkArrangementAnalysis()

    federal = _federal_work_arrangement(text)
    if federal is not None:
        return federal

    evidence: list[WorkArrangementEvidence] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for index, raw_line in enumerate(lines):
        metadata = _METADATA_LINE.fullmatch(raw_line)
        if metadata:
            arrangement = _canonical_arrangement(metadata.group("term"))
            if arrangement:
                tail = _clean_metadata_location(metadata.group("tail") or "")
                relation = _relation_for_arrangement(arrangement) if tail else "unknown"
                if not tail and index > 0 and _looks_like_location_line(lines[index - 1]):
                    tail = _normalize_location(lines[index - 1])
                    relation = "posting_location"
                evidence.append(
                    WorkArrangementEvidence(
                        arrangement=arrangement,
                        value=_ARRANGEMENT_LABELS[arrangement],
                        evidence=raw_line,
                        location=tail,
                        location_relation=relation,
                        confidence=0.98 if metadata.group("tail") else 0.96,
                        rule="metadata_arrangement_location" if metadata.group("tail") else "metadata_arrangement",
                    )
                )

        location_row = _LOCATION_ROW.fullmatch(raw_line)
        if location_row:
            parsed = _evidence_from_location_row(raw_line, location_row.group("body"))
            if parsed:
                evidence.append(parsed)

    for match in _JOINED_LOCATION_ROW.finditer(text):
        raw = " ".join(match.group(0).split())
        parsed = _evidence_from_location_row(raw, match.group("body"))
        if parsed:
            evidence.append(parsed)

    for match in _ARRANGEMENT_TOKEN.finditer(text):
        arrangement = _canonical_arrangement(match.group(0))
        if not arrangement or arrangement == "flexible":
            continue
        clause = _context_clause(text, match.start(), match.end())
        if _is_generic_policy_clause(clause):
            continue
        if _is_technical_usage(clause):
            continue
        if not _is_role_specific_arrangement(arrangement, clause):
            continue
        location, relation = _related_location(arrangement, clause, text)
        evidence.append(
            WorkArrangementEvidence(
                arrangement=arrangement,
                value=_ARRANGEMENT_LABELS[arrangement],
                evidence=clause,
                location=location,
                location_relation=relation,
                frequency=_frequency(clause),
                confidence=0.93,
                rule="prose_arrangement",
            )
        )

    has_remote_claim = any(item.arrangement == "remote" for item in evidence)
    for match in _PERIODIC_OFFICE.finditer(text):
        clause = " ".join(match.group("clause").split())
        if _is_generic_policy_clause(clause):
            continue
        location = _office_location(clause, text)
        arrangement = "on-site" if has_remote_claim else "hybrid"
        evidence.append(
            WorkArrangementEvidence(
                arrangement=arrangement,
                value=_ARRANGEMENT_LABELS[arrangement],
                evidence=clause,
                location=location,
                location_relation="office_location" if location else "unknown",
                frequency=_frequency(clause),
                confidence=0.96,
                rule="periodic_office_attendance",
            )
        )

    for match in _ATTENDANCE.finditer(text):
        clause = _context_clause(text, match.start(), match.end())
        if _is_generic_policy_clause(clause):
            continue
        location = _office_location(clause, text)
        if not location:
            city_state = _CITY_STATE.search(clause)
            location = _normalize_location(city_state.group(1)) if city_state else ""
        evidence.append(
            WorkArrangementEvidence(
                arrangement="on-site",
                value="On-site",
                evidence=clause,
                location=location,
                location_relation="office_location" if location else "unknown",
                frequency=_frequency(clause),
                confidence=0.94,
                rule="required_office_attendance",
            )
        )

    for match in _NOT_REMOTE.finditer(text):
        clause = _context_clause(text, match.start(), match.end())
        if _is_generic_policy_clause(clause):
            continue
        evidence.append(
            WorkArrangementEvidence(
                arrangement="on-site",
                value="On-site",
                evidence=clause,
                confidence=0.95,
                rule="explicit_not_remote",
            )
        )

    evidence = _dedupe_evidence(evidence)
    status, conflict = _resolve_status(evidence)
    return WorkArrangementAnalysis(
        status=status,
        location=_primary_location(evidence),
        evidence=tuple(evidence),
        conflict=conflict,
    )


def looks_like_work_arrangement_metadata(content: str) -> bool:
    """Return True when a short capture is itself a workplace badge or location row."""
    text = " ".join(str(content).split()).strip()
    if not text or len(text) > 220:
        return False
    if _REMOTE_TECHNICAL.search(text) or _HYBRID_TECHNICAL.search(text):
        return False
    if _METADATA_LINE.fullmatch(text):
        return True
    row = _LOCATION_ROW.fullmatch(text)
    return bool(row and _arrangement_from_location_body(row.group("body")))


def _federal_work_arrangement(text: str) -> WorkArrangementAnalysis | None:
    remote_no = _FEDERAL_REMOTE_NO.search(text)
    if not remote_no:
        return None
    telework = _TELEWORK_YES.search(text)
    if telework:
        detail = telework.group("detail") or ""
        value = (
            "Ad hoc telework eligible; not remote"
            if re.search(r"\bad[ -]?hoc\b", detail, re.IGNORECASE)
            else "Telework eligible; not remote"
        )
        item = WorkArrangementEvidence(
            arrangement="telework",
            value=value,
            evidence=_context_clause(text, telework.start(), telework.end()),
            confidence=0.99,
            rule="federal_telework_not_remote",
        )
        return WorkArrangementAnalysis(status=value, evidence=(item,))
    item = WorkArrangementEvidence(
        arrangement="on-site",
        value="On-site",
        evidence=_context_clause(text, remote_no.start(), remote_no.end()),
        confidence=0.99,
        rule="explicit_not_remote",
    )
    return WorkArrangementAnalysis(status="On-site", evidence=(item,))


def _evidence_from_location_row(raw: str, body: str) -> WorkArrangementEvidence | None:
    arrangement = _arrangement_from_location_body(body)
    if not arrangement:
        return None
    location = _clean_location_row_body(body)
    return WorkArrangementEvidence(
        arrangement=arrangement,
        value=_ARRANGEMENT_LABELS[arrangement],
        evidence=raw,
        location=location,
        location_relation=_relation_for_arrangement(arrangement) if location else "unknown",
        confidence=0.99,
        rule="location_row_arrangement",
    )


def _arrangement_from_location_body(body: str) -> str:
    lowered = " ".join(str(body).casefold().split())
    if re.search(r"\bhybrid\b", lowered):
        return "hybrid"
    if re.search(r"\b(?:fully\s+remote|remote)\b", lowered):
        return "remote"
    if re.search(r"\b(?:on[- ]?site|onsite|in[- ]office|in[- ]person)\b", lowered):
        return "on-site"
    if re.search(r"\bflexible\b", lowered):
        return "flexible"
    return ""


def _clean_location_row_body(body: str) -> str:
    candidate = re.sub(
        r"\(?\s*(?:on[- ]?site\s*[-/]\s*hybrid|hybrid\s*[-/]\s*on[- ]?site)\s*\)?",
        " ",
        body,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(rf"\b{_ARRANGEMENT_TERM}\b", " ", candidate, flags=re.IGNORECASE)
    return _clean_metadata_location(candidate)


def _canonical_arrangement(term: str) -> str:
    lowered = " ".join(str(term).casefold().split())
    if "remote" in lowered:
        return "remote"
    if "hybrid" in lowered:
        return "hybrid"
    if "telework" in lowered:
        return "telework"
    if "field" in lowered:
        return "field-based"
    if "flexible" in lowered:
        return "flexible"
    if any(
        value in lowered
        for value in (
            "onsite",
            "on-site",
            "on site",
            "in-office",
            "in office",
            "in-person",
            "in person",
        )
    ):
        return "on-site"
    return ""


def _relation_for_arrangement(arrangement: str) -> str:
    if arrangement == "remote":
        return "remote_eligibility"
    if arrangement in {"hybrid", "on-site"}:
        return "office_location"
    return "posting_location" if arrangement == "flexible" else "unknown"


def _is_technical_usage(clause: str) -> bool:
    return bool(_REMOTE_TECHNICAL.search(clause) or _HYBRID_TECHNICAL.search(clause))


def _is_generic_policy_clause(clause: str) -> bool:
    lowered = " ".join(clause.casefold().split())
    if "work personas" in lowered and "categories" in lowered:
        return True
    if "most roles" in lowered and ("hybrid" in lowered or "in-office" in lowered):
        return True
    if "all employees" in lowered and "hybrid working environment" in lowered:
        return True
    return False


def _is_role_specific_arrangement(arrangement: str, clause: str) -> bool:
    lowered = " ".join(clause.casefold().split())
    if arrangement == "remote":
        return bool(
            re.search(
                r"\b(?:remote|fully remote)\s+(?:role|position|job|work)\b|"
                r"\b(?:role|position|job)\b.{0,35}\b(?:is|will be|can be|may be)\s+"
                r"(?:fully\s+)?remote\b|"
                r"\bwork(?:ing)?\s+remotely\b|"
                r"\bremote(?:ly)?\s+(?:anywhere\s+)?(?:in|within|throughout)\b",
                lowered,
            )
        )
    if arrangement == "hybrid":
        return bool(
            re.search(
                r"\bhybrid\s+(?:role|position|job|work|schedule|model)\b|"
                r"\b(?:role|position|job)\b.{0,35}\b(?:is|will be)\s+hybrid\b|"
                r"\bhybrid\b.{0,70}\b(?:days?|times?)\b.{0,40}\b(?:week|month)\b",
                lowered,
            )
        )
    if arrangement == "on-site":
        return bool(
            re.search(
                r"\b(?:full[- ]?time\s+)?(?:on[- ]?site|onsite|in[- ]office|in[- ]person)\b"
                r".{0,50}\b(?:at|in|role|position|job|work|office)\b|"
                r"\b(?:role|position|job)\b.{0,35}\b(?:is|will be)\s+"
                r"(?:on[- ]?site|onsite|in[- ]office|in[- ]person)\b|"
                r"\([^)]*(?:on[- ]?site|onsite)[^)]*\)",
                lowered,
            )
        )
    if arrangement == "telework":
        return "telework eligible" in lowered
    if arrangement == "field-based":
        return bool(re.search(r"\bfield[- ]based\s+(?:role|position|job|work)\b", lowered))
    return False


def _related_location(arrangement: str, clause: str, full_text: str) -> tuple[str, str]:
    if arrangement == "remote":
        residence = _RESIDENCE.search(clause)
        if residence:
            location = _clean_location_phrase(residence.group("location"))
            if location:
                return location, "residence_requirement"
        scope = _REMOTE_SCOPE.search(clause)
        if scope:
            location = _clean_location_phrase(scope.group("location"))
            if location:
                return location, "remote_eligibility"
    if arrangement in {"hybrid", "on-site"}:
        location = _office_location(clause, full_text)
        if location:
            return location, "office_location"
        city_state = _CITY_STATE.search(clause)
        if city_state:
            return _normalize_location(city_state.group(1)), "office_location"
    return "", "unknown"


def _office_location(clause: str, full_text: str) -> str:
    direct = re.search(
        rf"\b(?:our\s+)?(?P<a>{_CITY_NAME},\s*{_STATE_CODES})\s+offices?\b|"
        rf"\boffices?\s+(?:located\s+)?in\s+(?P<b>{_CITY_NAME},\s*{_STATE_CODES})\b",
        clause,
    )
    if direct:
        return _normalize_location(direct.group("a") or direct.group("b") or "")

    city_after_office = re.search(
        rf"\boffices?\s+(?:located\s+)?in\s+(?P<city>{_CITY_NAME})\b",
        clause,
    )
    if city_after_office:
        return _infer_city_state(city_after_office.group("city"), full_text)

    city_state = _CITY_STATE.search(clause)
    if city_state and re.search(r"\boffice\b", clause, re.IGNORECASE):
        return _normalize_location(city_state.group(1))
    return ""


def _infer_city_state(city: str, full_text: str) -> str:
    city = " ".join(city.split()).strip(" ,")
    direct = re.search(
        rf"\b{re.escape(city)},\s*({_STATE_CODES})\b",
        full_text,
        re.IGNORECASE,
    )
    if direct:
        return f"{city}, {direct.group(1).upper()}"

    nearby = re.search(
        rf"\b{re.escape(city)}\b.{{0,120}}\b({'|'.join(map(re.escape, _STATE_NAME_TO_CODE))})\b",
        full_text,
        re.IGNORECASE | re.DOTALL,
    )
    if nearby:
        code = _STATE_NAME_TO_CODE.get(nearby.group(1).casefold())
        if code:
            return f"{city}, {code}"
    return city


def _clean_metadata_location(value: str) -> str:
    candidate = " ".join(str(value).strip(" \t-–—|•·:;()").split())
    if not candidate:
        return ""
    candidate = re.sub(rf"\b{_ARRANGEMENT_TERM}\b", " ", candidate, flags=re.IGNORECASE)
    candidate = " ".join(candidate.split()).strip(" -–—|•·:;()")
    if not candidate:
        return ""

    parts = [part.strip(" ,") for part in candidate.split(";") if part.strip(" ,")]
    normalized: list[str] = []
    for part in parts or [candidate]:
        lowered = part.casefold().strip(" .")
        if lowered in {"mx", "mexico"}:
            item = "Mexico"
        elif lowered in {"us", "u.s.", "usa", "u.s.a.", "united states"}:
            item = "United States"
        else:
            item = _normalize_location(part)
        if item and item.casefold() not in {value.casefold() for value in normalized}:
            normalized.append(item)

    if len(normalized) == 2 and set(value.casefold() for value in normalized) == {
        "mexico",
        "mx",
    }:
        return "Mexico"
    if normalized and all(value == "Mexico" for value in normalized):
        return "Mexico"
    if normalized and all(value == "United States" for value in normalized):
        return "United States"
    return "; ".join(normalized)[:180]


def _clean_location_phrase(value: str) -> str:
    candidate = " ".join(str(value).strip(" \t-–—|•·:,").split())
    candidate = re.split(
        r"\b(?:and|but|with|where|who|that|while|for)\b",
        candidate,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" ,")
    if not candidate:
        return ""
    city_state = _CITY_STATE.search(candidate)
    if city_state:
        return _normalize_location(city_state.group(1))
    if _US_COUNTRY.search(candidate):
        return "United States"
    states = _US_STATE_NAME.findall(candidate)
    if states:
        return ", ".join(dict.fromkeys(state.title() for state in states))
    codes = _US_STATE_CODE.findall(candidate)
    if codes and len(candidate) <= 100:
        return ", ".join(dict.fromkeys(code.upper() for code in codes))
    return _normalize_location(candidate) if 1 <= len(candidate.split()) <= 10 else ""


def _normalize_location(value: str) -> str:
    candidate = " ".join(str(value).split()).strip(" ,;|-–—")
    candidate = re.sub(r",\s*", ", ", candidate)
    candidate = re.sub(r",\s*United States(?: of America)?\s*$", "", candidate, flags=re.I)
    return candidate.strip(" ,")


def _looks_like_location_line(line: str) -> bool:
    text = " ".join(str(line).split()).strip()
    if not text or len(text) > 80 or _MONTH_DATE.search(text):
        return False
    if ":" in text or "$" in text or _ARRANGEMENT_TOKEN.fullmatch(text):
        return False
    if _CITY_STATE.search(text) or _US_COUNTRY.fullmatch(text) or _US_STATE_NAME.fullmatch(text):
        return True
    words = re.findall(r"[A-Za-z][A-Za-z.'-]*", text)
    if not 1 <= len(words) <= 4:
        return False
    blocked = {"engineering", "operations", "infrastructure", "product", "development"}
    if any(word.casefold() in blocked for word in words):
        return False
    return all(word[0].isupper() for word in words)


def _frequency(clause: str) -> str:
    match = _FREQUENCY.search(clause)
    return " ".join(match.group(0).split()) if match else ""


def _context_clause(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)

    sentence_start = max(
        text.rfind(".", line_start, start),
        text.rfind("!", line_start, start),
        text.rfind("?", line_start, start),
    )
    sentence_start = line_start if sentence_start < 0 else sentence_start + 1
    sentence_ends = [
        value
        for value in (
            text.find(".", end, line_end),
            text.find("!", end, line_end),
            text.find("?", end, line_end),
        )
        if value >= 0
    ]
    sentence_end = min(sentence_ends) + 1 if sentence_ends else line_end
    sentence = " ".join(text[sentence_start:sentence_end].split())
    if 0 < len(sentence) <= 360:
        return sentence
    return " ".join(text[line_start:line_end].split())[:360]


def _dedupe_evidence(items: list[WorkArrangementEvidence]) -> list[WorkArrangementEvidence]:
    result: list[WorkArrangementEvidence] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        key = (
            item.arrangement,
            item.evidence.casefold(),
            item.location.casefold(),
            item.location_relation,
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _resolve_status(evidence: list[WorkArrangementEvidence]) -> tuple[str, bool]:
    arrangements = {item.arrangement for item in evidence}
    if "remote" in arrangements and "on-site" in arrangements:
        return "Conflicting remote claim", True
    if "hybrid" in arrangements:
        return "Hybrid", False
    if "remote" in arrangements:
        return "Remote", False
    if "on-site" in arrangements:
        return "On-site", False
    if "flexible" in arrangements:
        return "Flexible", False
    if "telework" in arrangements:
        strongest = max(
            (item for item in evidence if item.arrangement == "telework"),
            key=lambda item: item.confidence,
        )
        return strongest.value, False
    if "field-based" in arrangements:
        return "Field-based", False
    return "", False


def _primary_location(evidence: list[WorkArrangementEvidence]) -> str:
    candidates = [item for item in evidence if item.location and item.location_relation != "unknown"]
    if not candidates:
        return ""
    priority = {
        "office_location": 4,
        "residence_requirement": 3,
        "remote_eligibility": 2,
        "posting_location": 1,
    }
    candidates.sort(
        key=lambda item: (priority.get(item.location_relation, 0), item.confidence),
        reverse=True,
    )
    return candidates[0].location


__all__ = [
    "WorkArrangementAnalysis",
    "WorkArrangementEvidence",
    "analyze_work_arrangement",
    "looks_like_work_arrangement_metadata",
]
