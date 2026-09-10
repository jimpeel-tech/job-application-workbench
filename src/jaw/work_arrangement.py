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
}

_ARRANGEMENT_TOKEN = re.compile(
    r"\b(?:fully\s+remote|remote|hybrid|on[- ]?site|onsite|in[- ]office|"
    r"in[- ]person|telework|field[- ]based)\b",
    re.IGNORECASE,
)
_METADATA_LINE = re.compile(
    r"^\s*(?P<term>fully\s+remote|remote|hybrid|on[- ]?site|onsite|"
    r"in[- ]office|in[- ]person|telework|field[- ]based)"
    r"(?:\s*(?:[-–—|•·:])\s*(?P<tail>.+?))?\s*$",
    re.IGNORECASE,
)
_REMOTE_TECHNICAL = re.compile(
    r"\bremote\s+(?:access|desktop|sensing|control|monitoring|procedure|"
    r"repository|server|shell|command|connection|endpoint|debugging)\b",
    re.IGNORECASE,
)
_HYBRID_TECHNICAL = re.compile(
    r"\bhybrid\s+(?:cloud|infrastructure|environment|architecture|network|"
    r"deployment|system|systems|platform)\b",
    re.IGNORECASE,
)
_ATTENDANCE = re.compile(
    r"\b(?:must|required|expected|need(?:ed)?|will|should)\b"
    r"[^.\n]{0,70}\b(?:report|commute|work|be)\b"
    r"[^.\n]{0,70}\b(?:office|on[- ]?site|onsite|in[- ]office|site|location)\b",
    re.IGNORECASE,
)
_NOT_REMOTE = re.compile(
    r"\b(?:not|isn't|is not|cannot be|can't be)\s+(?:a\s+)?remote\b|"
    r"\bremote\s+(?:work|option|arrangement)\s+(?:is\s+)?not\s+(?:available|offered|permitted)\b",
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
    r"\b(?:at least\s+)?(?:one|two|three|four|five|\d+)\s+days?\s+"
    r"(?:per|a|each)\s+week\b|"
    r"\b(?:once|twice|three times|four times|five times)\s+(?:per\s+week|weekly)\b|"
    r"\b(?:one|two|three|four|five|\d+)\s+times?\s+(?:per|a)\s+week\b",
    re.IGNORECASE,
)
_STATE_CODES = (
    r"(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|"
    r"MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|"
    r"TX|UT|VT|VA|WA|WV|WI|WY|DC)"
)
_CITY_NAME = r"(?:[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,4})"
_CITY_STATE = re.compile(rf"\b({_CITY_NAME},\s*{_STATE_CODES})\b")
_OFFICE_LOCATION = re.compile(
    rf"\b(?:our\s+)?(?P<location>{_CITY_NAME},\s*{_STATE_CODES})\s+office\b|"
    rf"\boffice\s+(?:located\s+)?in\s+(?P<location2>{_CITY_NAME},\s*{_STATE_CODES})\b"
)
_US_STATE_NAMES = (
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
    "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
    "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
    "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia",
    "Washington", "West Virginia", "Wisconsin", "Wyoming",
)
_US_STATE_NAME = re.compile(
    r"\b(?:" + "|".join(re.escape(value) for value in _US_STATE_NAMES) + r")\b",
    re.IGNORECASE,
)
_US_STATE_CODE = re.compile(rf"\b{_STATE_CODES}\b")
_US_COUNTRY = re.compile(
    r"\b(?:United States(?: of America)?|U\.?S\.?A?\.?)\b",
    re.IGNORECASE,
)
_RESIDENCE = re.compile(
    r"\b(?:must\s+(?:live|reside|be located)|residing|candidates?\s+(?:must\s+be\s+)?"
    r"(?:located|based)|employees?\s+(?:must\s+be\s+)?(?:located|based))\s+in\s+"
    r"(?P<location>[^.;\n]{2,100})",
    re.IGNORECASE,
)
_REMOTE_SCOPE = re.compile(
    r"\bremote(?:ly)?\s+(?:anywhere\s+)?(?:in|within|throughout)\s+"
    r"(?P<location>[^.;\n]{2,100})",
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
    """Extract work-arrangement evidence without collapsing location semantics too early."""
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return WorkArrangementAnalysis()

    evidence: list[WorkArrangementEvidence] = []

    federal_remote_no = _FEDERAL_REMOTE_NO.search(text)
    if federal_remote_no:
        telework = _TELEWORK_YES.search(text)
        if telework:
            detail = telework.group("detail") or ""
            value = (
                "Ad hoc telework eligible; not remote"
                if re.search(r"\bad[ -]?hoc\b", detail, re.IGNORECASE)
                else "Telework eligible; not remote"
            )
            evidence.append(
                WorkArrangementEvidence(
                    arrangement="telework",
                    value=value,
                    evidence=_context_clause(text, telework.start(), telework.end()),
                    confidence=0.99,
                    rule="federal_telework_not_remote",
                )
            )
            return WorkArrangementAnalysis(status=value, evidence=tuple(evidence))
        evidence.append(
            WorkArrangementEvidence(
                arrangement="on-site",
                value="On-site",
                evidence=_context_clause(text, federal_remote_no.start(), federal_remote_no.end()),
                confidence=0.99,
                rule="explicit_not_remote",
            )
        )
        return WorkArrangementAnalysis(status="On-site", evidence=tuple(evidence))

    for raw_line in (line.strip() for line in text.splitlines() if line.strip()):
        match = _METADATA_LINE.fullmatch(raw_line)
        if not match:
            continue
        arrangement = _canonical_arrangement(match.group("term"))
        if not arrangement:
            continue
        tail = _clean_metadata_location(match.group("tail") or "")
        relation = _relation_for_arrangement(arrangement) if tail else "unknown"
        evidence.append(
            WorkArrangementEvidence(
                arrangement=arrangement,
                value=_ARRANGEMENT_LABELS[arrangement],
                evidence=raw_line,
                location=tail,
                location_relation=relation,
                confidence=0.98 if tail else 0.96,
                rule="metadata_arrangement_location" if tail else "metadata_arrangement",
            )
        )

    for match in _iter_prose_arrangement_matches(text):
        arrangement = _canonical_arrangement(match.group(0))
        if not arrangement:
            continue
        clause = _context_clause(text, match.start(), match.end())
        location, relation = _related_location(arrangement, clause)
        evidence.append(
            WorkArrangementEvidence(
                arrangement=arrangement,
                value=_ARRANGEMENT_LABELS[arrangement],
                evidence=clause,
                location=location,
                location_relation=relation,
                frequency=_frequency(clause),
                confidence=0.90,
                rule="prose_arrangement",
            )
        )

    for match in _ATTENDANCE.finditer(text):
        clause = _context_clause(text, match.start(), match.end())
        location = _office_location(clause)
        if not location:
            city_state = _CITY_STATE.search(clause)
            location = city_state.group(1).strip() if city_state else ""
        evidence.append(
            WorkArrangementEvidence(
                arrangement="on-site",
                value="On-site",
                evidence=clause,
                location=location,
                location_relation="office_location" if location else "unknown",
                frequency=_frequency(clause),
                confidence=0.93,
                rule="required_office_attendance",
            )
        )

    for match in _NOT_REMOTE.finditer(text):
        clause = _context_clause(text, match.start(), match.end())
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
    """Return True for a short selection that itself looks like a work-arrangement badge/row."""
    text = " ".join(str(content).split()).strip()
    if not text or len(text) > 180:
        return False
    if _REMOTE_TECHNICAL.search(text) or _HYBRID_TECHNICAL.search(text):
        return False
    return bool(_METADATA_LINE.fullmatch(text))


def _iter_prose_arrangement_matches(text: str):
    for match in _ARRANGEMENT_TOKEN.finditer(text):
        window = text[max(0, match.start() - 20) : min(len(text), match.end() + 30)]
        if _REMOTE_TECHNICAL.search(window) or _HYBRID_TECHNICAL.search(window):
            continue
        term = match.group(0).casefold()
        lowered = _context_clause(text, match.start(), match.end()).casefold()
        if "remote" in term:
            if re.search(
                r"\b(?:remote|fully remote)\s+(?:role|position|job|work)\b|"
                r"\b(?:role|position|job)\b[^.\n]{0,30}\b(?:is|will be|can be|may be)\s+"
                r"(?:fully\s+)?remote\b|"
                r"\bwork(?:ing)?\s+remotely\b|"
                r"\bremote(?:ly)?\s+(?:anywhere\s+)?(?:in|within|throughout)\b",
                lowered,
            ):
                yield match
        elif "hybrid" in term:
            if re.search(
                r"\bhybrid\s+(?:role|position|job|work|schedule|model)\b|"
                r"\b(?:role|position|job)\b[^.\n]{0,30}\b(?:is|will be)\s+hybrid\b|"
                r"\bhybrid\b[^.\n]{0,60}\b(?:days?|times?)\b[^.\n]{0,30}\bweek\b",
                lowered,
            ):
                yield match
        elif re.search(r"on[- ]?site|onsite|in[- ]office|in[- ]person", term):
            if re.search(
                r"\b(?:on[- ]?site|onsite|in[- ]office|in[- ]person)\s+"
                r"(?:role|position|job|work)\b|"
                r"\b(?:role|position|job)\b[^.\n]{0,30}\b(?:is|will be)\s+"
                r"(?:on[- ]?site|onsite|in[- ]office|in[- ]person)\b",
                lowered,
            ):
                yield match
        elif "telework" in term or "field" in term:
            yield match


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
    if any(value in lowered for value in (
        "onsite", "on-site", "on site", "in-office", "in office", "in-person", "in person"
    )):
        return "on-site"
    return ""


def _relation_for_arrangement(arrangement: str) -> str:
    if arrangement == "remote":
        return "remote_eligibility"
    if arrangement in {"hybrid", "on-site"}:
        return "office_location"
    return "unknown"


def _clean_metadata_location(value: str) -> str:
    candidate = " ".join(value.strip(" \t-–—|•·:").split())
    if not candidate:
        return ""
    if re.fullmatch(
        r"(?:full[- ]?time|part[- ]?time|contract(?:or)?|temporary|permanent|internship)",
        candidate,
        re.IGNORECASE,
    ):
        return ""
    return candidate[:140]


def _related_location(arrangement: str, clause: str) -> tuple[str, str]:
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
        location = _office_location(clause)
        if location:
            return location, "office_location"
        city_state = _CITY_STATE.search(clause)
        if city_state:
            return city_state.group(1).strip(), "office_location"
    return "", "unknown"


def _clean_location_phrase(value: str) -> str:
    candidate = " ".join(value.strip(" \t-–—|•·:,").split())
    candidate = re.split(
        r"\b(?:and|but|with|where|who|that|while|for)\b",
        candidate,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" ,")
    city_state = _CITY_STATE.search(candidate)
    if city_state:
        return city_state.group(1).strip()
    if _US_COUNTRY.search(candidate):
        return "United States"
    states = _US_STATE_NAME.findall(candidate)
    if states:
        return ", ".join(dict.fromkeys(state.title() for state in states))
    codes = _US_STATE_CODE.findall(candidate)
    if codes and len(candidate) <= 80:
        return ", ".join(dict.fromkeys(code.upper() for code in codes))
    return candidate[:100] if 1 <= len(candidate.split()) <= 8 else ""


def _office_location(clause: str) -> str:
    match = _OFFICE_LOCATION.search(clause)
    if match:
        return (match.group("location") or match.group("location2") or "").strip()
    return ""


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
    if 0 < len(sentence) <= 320:
        return sentence

    line = " ".join(text[line_start:line_end].split())
    return line[:320]


def _dedupe_evidence(items: list[WorkArrangementEvidence]) -> list[WorkArrangementEvidence]:
    result: list[WorkArrangementEvidence] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        key = (item.arrangement, item.evidence.casefold(), item.location.casefold(), item.rule)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _resolve_status(evidence: list[WorkArrangementEvidence]) -> tuple[str, bool]:
    arrangements = {item.arrangement for item in evidence}
    if "hybrid" in arrangements:
        return "Hybrid", False
    if "remote" in arrangements and "on-site" in arrangements:
        return "Conflicting remote claim", True
    if "remote" in arrangements:
        return "Remote", False
    if "on-site" in arrangements:
        return "On-site", False
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
    candidates = [
        item for item in evidence if item.location and item.location_relation != "unknown"
    ]
    if not candidates:
        return ""
    priority = {
        "office_location": 3,
        "residence_requirement": 2,
        "remote_eligibility": 1,
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
