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
_IDENTITY_NON_COMPANY_VALUES = {
    "about us",
    "basic qualifications",
    "benefits",
    "company description",
    "full job description",
    "job description",
    "job details",
    "job type",
    "location",
    "locations",
    "minimum qualifications",
    "qualifications",
    "remote",
    "requirements",
    "responsibilities",
    "work type",
}
_IDENTITY_TITLE = re.compile(
    r"\b(?:administrator|analyst|architect|consultant|developer|director|engineer|"
    r"engineering|lead|manager|officer|principal|scientist|specialist|technician|"
    r"sre|devops|devsecops)\b",
    re.IGNORECASE,
)
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

    identity = _identity_company_candidate(content)
    if identity is not None:
        value, evidence = identity
        candidates[value.casefold()] = {
            "value": value,
            "confidence": 1.0,
            "count": 2,
            "evidence": evidence,
            "rule": "capture_identity_pair",
        }

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

    full_time_exempt_header = re.search(
        r"(?:^|\n)\s*Full[\s-]*Time(?:\s+Regular)?\s*\n\s*"
        r"(?:Staff\s*[-–—]\s*)?Exempt\b",
        content,
        re.IGNORECASE,
    )
    if full_time_exempt_header:
        return GeneralFieldEvidence(
            field="employment_type",
            value="Full-time, exempt",
            evidence=_context_window(
                content,
                full_time_exempt_header.start(),
                full_time_exempt_header.end(),
            ),
            confidence=0.995,
            rule="full_time_exempt_metadata",
        )

    weekly_hours = re.search(
        r"\b(?:you(?:['’]ll|\s+will)\s+be\s+)?working\s+40\s+hours?\s+"
        r"(?:a|per)\s+week\b",
        content,
        re.IGNORECASE,
    )
    if weekly_hours:
        return GeneralFieldEvidence(
            field="employment_type",
            value="Full-time, 40 hours per week",
            evidence=_context_line(content, weekly_hours.start(), weekly_hours.end()),
            confidence=0.99,
            rule="explicit_40_hour_workweek",
        )

    scheduled_weekly_hours = re.search(
        r"(?:^|\n)\s*Scheduled\s+Weekly\s+Hours\s*:\s*(?:\n\s*)?40\b",
        content,
        re.IGNORECASE,
    )
    if scheduled_weekly_hours:
        return GeneralFieldEvidence(
            field="employment_type",
            value="Full-time",
            evidence=_context_window(
                content,
                scheduled_weekly_hours.start(),
                scheduled_weekly_hours.end(),
            ),
            confidence=0.99,
            rule="scheduled_weekly_hours_full_time",
        )

    employment_basis = re.search(
        r"\bbased\s+on\s+(?P<value>full[\s-]*time|part[\s-]*time)\s+employment\b",
        content,
        re.IGNORECASE,
    )
    if employment_basis:
        value = _normalize_employment_type(employment_basis.group("value"))
        if value:
            return GeneralFieldEvidence(
                field="employment_type",
                value=value,
                evidence=_context_line(content, employment_basis.start(), employment_basis.end()),
                confidence=0.99,
                rule="explicit_employment_basis",
            )

    based_workload = re.search(
        r"\bbased\s+(?P<value>full[\s-]*time|part[\s-]*time)\s+in\b",
        content,
        re.IGNORECASE,
    )
    if based_workload:
        value = _normalize_employment_type(based_workload.group("value"))
        if value:
            return GeneralFieldEvidence(
                field="employment_type",
                value=value,
                evidence=_context_line(content, based_workload.start(), based_workload.end()),
                confidence=0.99,
                rule="based_workload_prose",
            )

    standalone_workload = re.search(
        r"(?:^|\n)\s*(?P<value>Full[\s-]*time|Part[\s-]*time)\b"
        r"(?:\s*,\s*[^\n]{2,80})?\s*(?:\n|$)",
        content,
        re.IGNORECASE,
    )
    if standalone_workload:
        value = _normalize_employment_type(standalone_workload.group("value"))
        if value:
            return GeneralFieldEvidence(
                field="employment_type",
                value=value,
                evidence=_context_line(content, standalone_workload.start(), standalone_workload.end()),
                confidence=0.985,
                rule="standalone_workload_metadata",
            )

    # The current scalar employment_type field primarily represents workload
    # classification (full-time/part-time/contract). When a posting also exposes
    # an HR relationship such as "Regular Employee", prefer an explicit statement
    # that the role itself is full-time or part-time.
    prose_patterns = (
        re.compile(
            r"\b(?:this|the)\s+(?:position|role|job)\s+(?:will\s+be|is)\s+"
            r"(?P<value>(?:permanent\s+)?(?:full[- ]time|part[- ]time)"
            r"(?:\s*,?\s*(?:exempt|salaried|contract))?)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bthis\s+is\s+an?\s+"
            r"(?P<value>(?:permanent\s+)?(?:full[- ]time|part[- ]time)"
            r"(?:\s*,?\s*(?:exempt|salaried|contract))?)\s+"
            r"(?:position|role|job)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bthis\s+"
            r"(?P<value>(?:permanent\s+)?(?:full[- ]time|part[- ]time)"
            r"(?:\s*,?\s*(?:exempt|salaried|contract))?)\s+"
            r"(?:position|role|job)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bthis\s+is\s+an?\s+"
            r"(?P<value>permanent|temporary|seasonal|contract)\s+"
            r"(?:position|role|job)\b",
            re.IGNORECASE,
        ),
    )
    for pattern in prose_patterns:
        match = pattern.search(content)
        if match:
            value = _normalize_employment_type(match.group("value"))
            if value:
                return GeneralFieldEvidence(
                    field="employment_type",
                    value=value,
                    evidence=_context_line(content, match.start(), match.end()),
                    confidence=0.995,
                    rule="employment_type_prose",
                )

    labeled_patterns = (
        (
            re.compile(
                r"(?:^|\n)\s*(?:Employment\s+Type|Employment\s+Status|Job\s+Types?|"
                r"Time\s+Type|Position\s+Type|Contract\s+Type)\s*:?\s*(?:\n\s*)?"
                r"(?P<value>[^\n|•]{2,90})",
                re.IGNORECASE,
            ),
            "explicit_employment_type_label",
        ),
        (
            re.compile(
                r"(?:^|\n)\s*Type\s*:\s*(?P<value>[^\n|•]{2,90})",
                re.IGNORECASE,
            ),
            "generic_type_label",
        ),
    )
    for pattern, rule in labeled_patterns:
        for match in pattern.finditer(content):
            value = _normalize_employment_type(match.group("value"))
            if value:
                return GeneralFieldEvidence(
                    field="employment_type",
                    value=value,
                    evidence=_context_line(content, match.start(), match.end()),
                    confidence=0.99,
                    rule=rule,
                )

    benefit_type = re.search(
        r"\bBenefit\s+Type\b[^\n]{0,80}\bSalaried\b[^\n]{0,50}\bFull[- ]Time\b",
        content,
        re.IGNORECASE,
    )
    if benefit_type:
        return GeneralFieldEvidence(
            field="employment_type",
            value="Full-time salaried",
            evidence=_context_line(content, benefit_type.start(), benefit_type.end()),
            confidence=0.98,
            rule="benefit_type_salaried_full_time",
        )

    compact = re.search(
        r"(?:^|\n)[^\n]{0,100}(?:·|\|)\s*"
        r"(?P<value>Full[- ]time|Part[- ]time|Permanent|Temporary|Seasonal|Contract)\b",
        content,
        re.IGNORECASE,
    )
    if compact:
        value = _normalize_employment_type(compact.group("value"))
        if value:
            return GeneralFieldEvidence(
                field="employment_type",
                value=value,
                evidence=_context_line(content, compact.start(), compact.end()),
                confidence=0.96,
                rule="compact_employment_metadata",
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

    obtain = re.search(
        r"\bmust\s+be\s+able\s+to\s+obtain\s+(?:a\s+)?security\s+clearance\b",
        content,
        re.IGNORECASE,
    )
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


def _identity_company_candidate(content: str) -> tuple[str, str] | None:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", content.strip()) if block.strip()]
    if len(blocks) < 2:
        return None

    first = _identity_block_value(blocks[0])
    second = _identity_block_value(blocks[1])
    if _looks_like_company_identity(first) and _looks_like_title_identity(second):
        return first, " | ".join((first, second))
    if _looks_like_title_identity(first) and _looks_like_company_identity(second):
        return second, " | ".join((first, second))
    return None


def _identity_block_value(block: str) -> str:
    lines = [" ".join(line.split()).strip() for line in block.splitlines() if line.strip()]
    if not lines or len(lines) > 3:
        return ""

    cleaned = [_clean_company(line) for line in lines]
    cleaned = [value for value in cleaned if value]
    if not cleaned:
        return ""

    unique = list(dict.fromkeys(value.casefold() for value in cleaned))
    if len(unique) == 1:
        return cleaned[0]
    if len(cleaned) == 1:
        return cleaned[0]
    return ""


def _looks_like_company_identity(value: str) -> bool:
    if not _valid_company(value) or _looks_like_title_identity(value):
        return False
    lowered = value.casefold().strip()
    if lowered in _IDENTITY_NON_COMPANY_VALUES:
        return False
    if any(marker in value for marker in (":", "|", "·", "$", "?")):
        return False
    if re.search(r"\b(?:remote|hybrid|on[- ]?site|full[- ]?time|part[- ]?time)\b", lowered):
        return False
    return bool(re.search(r"[A-Za-z]", value))


def _looks_like_title_identity(value: str) -> bool:
    if not value or len(value) > 140:
        return False
    return bool(_IDENTITY_TITLE.search(value))


def _normalize_employment_type(value: str) -> str:
    raw = " ".join(str(value).split()).strip(" \t:;,.")
    lowered = raw.casefold().replace("–", "-").replace("—", "-")
    lowered = re.sub(r"\bfull[\s-]*time\b", "full-time", lowered)
    lowered = re.sub(r"\bpart[\s-]*time\b", "part-time", lowered)
    lowered = re.sub(r"\bcontract[\s-]*to[\s-]*hire\b", "contract to hire", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()

    if "contract to hire" in lowered:
        return "Contract to hire"
    if re.search(r"\bregular employee\b", lowered):
        return "Regular employee"
    if "permanent" in lowered and "full-time" in lowered:
        return "Permanent, full-time"
    if "full-time" in lowered and "contract" in lowered:
        if re.search(r"full-time\s*(?:,|/|\bor\b)\s*contract", lowered):
            return "Full-time or contract"
        return "Full-time contract"
    if "hourly" in lowered and "contract" in lowered:
        return "Hourly contract"
    if "full-time" in lowered and "exempt" in lowered:
        return "Full-time, exempt"
    if "full-time" in lowered and "salaried" in lowered:
        return "Full-time salaried"
    if "part-time" in lowered and "contract" in lowered:
        return "Part-time contract"
    if "full-time" in lowered:
        return "Full-time"
    if "part-time" in lowered:
        return "Part-time"
    if re.search(r"\bpermanent\b", lowered):
        return "Permanent"
    if re.search(r"\btemporary\b", lowered):
        return "Temporary"
    if re.search(r"\bseasonal\b", lowered):
        return "Seasonal"
    if re.search(r"\bcontract\b", lowered):
        return "Contract"
    return ""


def _employment_label(value: str) -> str:
    normalized = _normalize_employment_type(value)
    return normalized or value.strip().title()


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
