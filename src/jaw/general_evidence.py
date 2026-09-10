from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GeneralFieldEvidence:
    field: str
    value: str
    evidence: str
    confidence: float
    rule: str


_LOCATION_LIKE = re.compile(
    r"^(?:US,\s*)?[A-Za-z.' -]{2,70},\s*(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)(?:,\s*(?:United States|USA|US))?$",
    re.IGNORECASE,
)
_GENERIC_COMPANY_VALUES = {
    "company",
    "company description",
    "employer",
    "organization",
    "today",
    "united states",
    "job description",
    "job details",
    "location",
    "locations",
}
_COMPANY_PATTERNS: tuple[tuple[re.Pattern[str], float, str], ...] = (
    (
        re.compile(r"(?:^|\n)\s*Company\s+logo\s+for,?\s*([^\n]{2,100})", re.IGNORECASE),
        1.0,
        "company_logo_label",
    ),
    (
        re.compile(r"(?:^|\n)\s*(?:Company|Employer|Organization)\s*:\s*([^\n]{2,100})", re.IGNORECASE),
        1.0,
        "explicit_company_label",
    ),
    (
        re.compile(r"(?:^|[.!?]\s+|\n)Today,\s*([A-Z][A-Za-z0-9&'’.\- ]{1,70}?)\s+is\b"),
        0.97,
        "today_company_is",
    ),
    (
        re.compile(r"(?:^|[.!?]\s+|\n)([A-Z][A-Za-z0-9&'’.\- ]{1,70}?)\s+was\s+founded\b"),
        0.98,
        "company_was_founded",
    ),
    (
        re.compile(r"(?:^|[.!?]\s+|\n)([A-Z][A-Za-z0-9&'’.\- ]{1,70}?)\s+is\s+(?:looking|seeking|hiring)\b"),
        0.98,
        "company_is_hiring",
    ),
    (
        re.compile(r"(?:^|[.!?]\s+|\n)At\s+([A-Z][A-Za-z0-9&'’.\- ]{1,70}?),\s+(?:we|our|you)\b"),
        0.96,
        "at_company",
    ),
    (
        re.compile(r"(?:^|\n)([A-Z][A-Za-z0-9&'’.\- ]{1,70}?)\s+US\s+offers\b"),
        0.96,
        "company_us_offers",
    ),
    (
        re.compile(r"\b([A-Z][A-Za-z0-9&'’.\- ]{1,70}?)['’]s\s+offices?\b"),
        0.93,
        "company_office_possessive",
    ),
)

_NEGATIVE_ON_CALL = re.compile(
    r"\b(?:no|not|without)\s+(?:an?\s+)?on[- ]call\b|"
    r"\bno\s+on[- ]call\s+rotations?\b|"
    r"\bon[- ]call\s+(?:is\s+)?not\s+(?:required|expected)\b",
    re.IGNORECASE,
)
_POSITIVE_ON_CALL: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b(?:participat(?:e|es|ing)|take\s+part|serve)\b[^.\n]{0,55}"
            r"\bon[- ]call\s+rotations?\b",
            re.IGNORECASE,
        ),
        "participates_on_call_rotation",
    ),
    (
        re.compile(
            r"\b(?:must|required|expected|available|willing)\b[^.\n]{0,65}"
            r"\bon[- ]call(?:\s+rotations?)?\b",
            re.IGNORECASE,
        ),
        "explicit_on_call_requirement",
    ),
    (
        re.compile(
            r"\bon[- ]call\s+rotations?\b[^.\n]{0,45}\b(?:required|expected|mandatory)\b",
            re.IGNORECASE,
        ),
        "on_call_rotation_required",
    ),
    (
        re.compile(r"\bpager\s+duty\b", re.IGNORECASE),
        "pager_duty",
    ),
)
_ON_CALL_PRACTICE_ONLY = re.compile(
    r"\b(?:establish|define|build|design|create|improve|manage|develop|own)\w*\b"
    r"[^.\n]{0,90}\bon[- ]call\s+(?:practice|practices|process|processes|program|programs|"
    r"policy|policies|standard|standards|procedure|procedures)\b",
    re.IGNORECASE,
)

_DATE = (
    r"(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},\s+\d{4}"
)
_CLEARANCE_LIST = re.compile(
    r"\b((?:Active\s+|Current\s+)?Top\s+Secret"
    r"(?:\s*,\s*Top\s+Secret\s+SCI)?"
    r"(?:\s*,?\s*(?:or|and)\s*DOE\s+Level\s+[A-Z0-9]+)?\s+clearance)\b",
    re.IGNORECASE,
)
_CLEARANCE_GENERIC = re.compile(
    r"\b((?:active\s+|current\s+)?(?:top\s+secret(?:/SCI|\s+SCI)?|secret|public\s+trust)"
    r"\s+(?:security\s+)?clearance)\b",
    re.IGNORECASE,
)


def extract_general_evidence(content: str) -> tuple[GeneralFieldEvidence, ...]:
    """Extract high-confidence general facts independently of domain-specific parsing."""
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return ()

    evidence: list[GeneralFieldEvidence] = []
    extractors = (
        extract_company_evidence,
        extract_on_call_evidence,
        extract_employment_type_evidence,
        extract_clearance_evidence,
        extract_sponsorship_evidence,
        extract_travel_evidence,
        extract_application_deadline_evidence,
    )
    for extractor in extractors:
        item = extractor(text)
        if item is not None:
            evidence.append(item)
    return tuple(evidence)


def extract_company_evidence(content: str) -> GeneralFieldEvidence | None:
    candidates: dict[str, dict[str, object]] = {}
    for pattern, confidence, rule in _COMPANY_PATTERNS:
        for match in pattern.finditer(content):
            value = _clean_company(match.group(1))
            if not _valid_company(value):
                continue
            key = value.casefold()
            current = candidates.setdefault(
                key,
                {
                    "value": value,
                    "confidence": confidence,
                    "count": 0,
                    "evidence": _context_line(content, match.start(), match.end()),
                    "rule": rule,
                },
            )
            current["count"] = int(current["count"]) + 1
            if confidence > float(current["confidence"]):
                current["value"] = value
                current["confidence"] = confidence
                current["evidence"] = _context_line(content, match.start(), match.end())
                current["rule"] = rule

    if not candidates:
        return None

    best = max(
        candidates.values(),
        key=lambda item: (
            min(1.0, float(item["confidence"]) + 0.01 * (int(item["count"]) - 1)),
            int(item["count"]),
            len(str(item["value"])),
        ),
    )
    confidence = min(1.0, float(best["confidence"]) + 0.01 * (int(best["count"]) - 1))
    return GeneralFieldEvidence(
        field="company",
        value=str(best["value"]),
        evidence=str(best["evidence"]),
        confidence=confidence,
        rule=str(best["rule"]),
    )


def extract_on_call_evidence(content: str) -> GeneralFieldEvidence | None:
    negative = _NEGATIVE_ON_CALL.search(content)
    if negative:
        return GeneralFieldEvidence(
            field="on_call",
            value="Not required",
            evidence=_context_line(content, negative.start(), negative.end()),
            confidence=0.99,
            rule="explicit_no_on_call",
        )

    for pattern, rule in _POSITIVE_ON_CALL:
        for match in pattern.finditer(content):
            clause = _context_line(content, match.start(), match.end())
            if _ON_CALL_PRACTICE_ONLY.search(clause):
                continue
            return GeneralFieldEvidence(
                field="on_call",
                value="Required",
                evidence=clause,
                confidence=0.98,
                rule=rule,
            )
    return None


def extract_employment_type_evidence(content: str) -> GeneralFieldEvidence | None:
    contract = re.search(
        r"\bContract\s+Length\s*:\s*[^\n]{0,80}?\bContract\s+to\s+Hire\b",
        content,
        re.IGNORECASE,
    )
    if contract:
        return GeneralFieldEvidence(
            field="employment_type",
            value="Contract to hire",
            evidence=_context_line(content, contract.start(), contract.end()),
            confidence=0.99,
            rule="contract_length_to_hire",
        )

    labeled = re.search(
        r"\b(?:Employment\s+Type|Job\s+Type|Time\s+Type)\s*:?\s*(?:\n\s*)?"
        r"(Full[- ]time|Part[- ]time|Temporary|Seasonal|Permanent)\b",
        content,
        re.IGNORECASE,
    )
    if labeled:
        return GeneralFieldEvidence(
            field="employment_type",
            value=_employment_label(labeled.group(1)),
            evidence=_context_line(content, labeled.start(), labeled.end()),
            confidence=0.99,
            rule="explicit_employment_type_label",
        )

    prose = re.search(
        r"\b(?:this|the)\s+(?:position|role|job)\s+(?:will\s+be|is)\s+"
        r"(full[- ]time|part[- ]time)\b",
        content,
        re.IGNORECASE,
    )
    if prose:
        return GeneralFieldEvidence(
            field="employment_type",
            value=_employment_label(prose.group(1)),
            evidence=_context_line(content, prose.start(), prose.end()),
            confidence=0.98,
            rule="employment_type_prose",
        )
    return None


def extract_clearance_evidence(content: str) -> GeneralFieldEvidence | None:
    negative = re.search(
        r"Does\s+this\s+position\s+require\s+(?:a\s+)?security\s+clearance\s*\?\s*"
        r"(?:\n\s*)?No\b|"
        r"\bSecurity\s+clearance\s*:\s*No\b",
        content,
        re.IGNORECASE,
    )
    if negative:
        return GeneralFieldEvidence(
            field="clearance",
            value="No",
            evidence=_context_window(content, negative.start(), negative.end()),
            confidence=1.0,
            rule="explicit_clearance_no",
        )

    candidates: list[tuple[int, re.Match[str], str]] = []
    for match in _CLEARANCE_LIST.finditer(content):
        value = re.sub(r"\s+", " ", match.group(1)).strip()
        score = 10 + value.count(",") + 2 * bool(re.search(r"\bDOE\s+Level\b", value, re.I))
        candidates.append((score, match, value))
    for match in _CLEARANCE_GENERIC.finditer(content):
        value = re.sub(r"\s+", " ", match.group(1)).strip()
        candidates.append((3, match, value))
    if candidates:
        _, match, value = max(candidates, key=lambda item: (item[0], len(item[2]), -item[1].start()))
        return GeneralFieldEvidence(
            field="clearance",
            value=value,
            evidence=_context_line(content, match.start(), match.end()),
            confidence=0.99,
            rule="explicit_clearance_requirement",
        )

    obtain = re.search(r"\bmust\s+be\s+able\s+to\s+obtain\s+(?:a\s+)?security\s+clearance\b", content, re.I)
    if obtain:
        return GeneralFieldEvidence(
            field="clearance",
            value="Must be able to obtain",
            evidence=_context_line(content, obtain.start(), obtain.end()),
            confidence=0.97,
            rule="clearance_obtainable",
        )
    return None


def extract_sponsorship_evidence(content: str) -> GeneralFieldEvidence | None:
    negative_patterns = (
        r"\b(?:visa\s*/\s*work\s+permit|visa|immigration|work\s+permit)?\s*"
        r"sponsorship\s+is\s+not\s+available\b",
        r"\b(?:position|role|job)\s+is\s+not\s+eligible\s+for\s+(?:visa\s+)?sponsorship\b",
        r"\bnot\s+(?:currently\s+)?(?:able\s+to\s+)?sponsor\b[^.\n]{0,90}"
        r"(?:sponsorship|H-1B|TN|OPT|O-1|L-1)?",
        r"\b(?:will|do)\s+not\s+(?:provide|offer)\b[^.\n]{0,60}\b(?:visa|sponsorship)\b",
        r"\bno\s+(?:visa\s+)?sponsorship\b",
    )
    for pattern in negative_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return GeneralFieldEvidence(
                field="sponsorship",
                value="Not offered",
                evidence=_context_line(content, match.start(), match.end()),
                confidence=0.99,
                rule="explicit_sponsorship_denial",
            )

    available = re.search(
        r"\b(?:visa|immigration)\s+sponsorship\s+(?:is\s+)?available\b",
        content,
        re.IGNORECASE,
    )
    if available:
        return GeneralFieldEvidence(
            field="sponsorship",
            value="Available",
            evidence=_context_line(content, available.start(), available.end()),
            confidence=0.98,
            rule="explicit_sponsorship_available",
        )
    return None


def extract_travel_evidence(content: str) -> GeneralFieldEvidence | None:
    less_than = re.search(
        r"\btravel\b[^.\n]{0,120}?\(\s*(<\s*\d{1,3}\s*%)\s*\)",
        content,
        re.IGNORECASE,
    )
    if less_than:
        value = re.sub(r"\s+", "", less_than.group(1))
        return GeneralFieldEvidence(
            field="travel",
            value=value,
            evidence=_context_line(content, less_than.start(), less_than.end()),
            confidence=0.99,
            rule="travel_less_than_percent",
        )

    up_to = re.search(
        r"(?:\btravel(?:\s+requirements?)?\s*:?\s*|\btravel\b[^.\n]{0,60}?)"
        r"(?:up\s+to\s+)(\d{1,3}\s*%)",
        content,
        re.IGNORECASE,
    )
    if up_to:
        return GeneralFieldEvidence(
            field="travel",
            value=f"Up to {up_to.group(1).replace(' ', '')}",
            evidence=_context_line(content, up_to.start(), up_to.end()),
            confidence=0.98,
            rule="travel_up_to_percent",
        )

    none = re.search(r"\bno\s+travel\s+(?:is\s+)?required\b", content, re.IGNORECASE)
    if none:
        return GeneralFieldEvidence(
            field="travel",
            value="None",
            evidence=_context_line(content, none.start(), none.end()),
            confidence=0.99,
            rule="explicit_no_travel",
        )
    return None


def extract_application_deadline_evidence(content: str) -> GeneralFieldEvidence | None:
    accepted_until = re.search(
        rf"\bApplications?\s+(?:for\s+this\s+job\s+)?will\s+be\s+accepted\s+"
        rf"(?:at\s+least\s+)?until\s+({_DATE})\b",
        content,
        re.IGNORECASE,
    )
    if accepted_until:
        return GeneralFieldEvidence(
            field="application_deadline",
            value=accepted_until.group(1),
            evidence=_context_line(content, accepted_until.start(), accepted_until.end()),
            confidence=0.99,
            rule="applications_accepted_until",
        )

    explicit = re.search(
        rf"\b(?:application|apply|closing)\s+(?:deadline|date)\s*:?\s*({_DATE})\b",
        content,
        re.IGNORECASE,
    )
    if explicit:
        return GeneralFieldEvidence(
            field="application_deadline",
            value=explicit.group(1),
            evidence=_context_line(content, explicit.start(), explicit.end()),
            confidence=0.99,
            rule="explicit_application_deadline",
        )
    return None


def _employment_label(value: str) -> str:
    lowered = re.sub(r"\s+", "-", value.strip().casefold())
    if lowered == "full-time":
        return "Full-time"
    if lowered == "part-time":
        return "Part-time"
    return value.strip().title()


def _clean_company(value: str) -> str:
    candidate = " ".join(str(value).split()).strip(" \t,;:-")
    candidate = re.sub(r"^Company\s+logo\s+for,?\s*", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"^Today,\s*", "", candidate, flags=re.IGNORECASE)
    return candidate.strip(" \t,;:-.")


def _valid_company(value: str) -> bool:
    if not value:
        return False
    normalized = value.casefold()
    if normalized in _GENERIC_COMPANY_VALUES or len(value) > 90:
        return False
    if _LOCATION_LIKE.fullmatch(value):
        return False
    if re.match(r"^US,\s*[A-Z]{2},\s*", value):
        return False
    words = value.split()
    if not 1 <= len(words) <= 8:
        return False
    if any(token in normalized for token in (" job ", " position ", " role ")):
        return False
    return True


def _context_line(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    line = " ".join(text[line_start:line_end].split())
    return line[:360]


def _context_window(text: str, start: int, end: int) -> str:
    return " ".join(text[max(0, start - 80):min(len(text), end + 80)].split())[:360]


__all__ = [
    "GeneralFieldEvidence",
    "extract_application_deadline_evidence",
    "extract_clearance_evidence",
    "extract_company_evidence",
    "extract_employment_type_evidence",
    "extract_general_evidence",
    "extract_on_call_evidence",
    "extract_sponsorship_evidence",
    "extract_travel_evidence",
]
