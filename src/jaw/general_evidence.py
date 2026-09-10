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


def extract_general_evidence(content: str) -> tuple[GeneralFieldEvidence, ...]:
    """Extract high-confidence general facts independently of domain-specific parsing."""
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return ()

    evidence: list[GeneralFieldEvidence] = []
    company = extract_company_evidence(text)
    if company is not None:
        evidence.append(company)
    on_call = extract_on_call_evidence(text)
    if on_call is not None:
        evidence.append(on_call)
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


__all__ = [
    "GeneralFieldEvidence",
    "extract_company_evidence",
    "extract_general_evidence",
    "extract_on_call_evidence",
]
