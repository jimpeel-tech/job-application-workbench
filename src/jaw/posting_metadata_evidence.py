from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PostingMetadataEvidence:
    field: str
    value: str
    evidence: str
    confidence: float
    rule: str


_AT_COMPANY = re.compile(
    r"(?:^|[.!?]\s+|\n)At\s+"
    r"(?P<company>[A-Z][A-Za-z0-9&'’.\- ]{1,70}?)"
    r"(?:\s*[®™])?,\s+(?:we|our|you)\b",
)
_SPONSORSHIP_ELIGIBILITY = re.compile(
    r"\bIs\s+(?:this\s+)?(?:role|position|job)\s+eligible\s+for\s+"
    r"(?:immigration|visa)\s+sponsorship\s*\?\s*:?\s*"
    r"(?:\n[ \t]*)?(?P<answer>Yes|No)\b",
    re.IGNORECASE,
)
_STATE_OR_PROVINCE = (
    r"(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|"
    r"MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|"
    r"TX|UT|VT|VA|WA|WV|WI|WY|DC|"
    r"Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|"
    r"Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|"
    r"Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|"
    r"Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|"
    r"New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|"
    r"Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|"
    r"Virginia|Washington|West Virginia|Wisconsin|Wyoming|District of Columbia|"
    r"Alberta|British Columbia|Manitoba|New Brunswick|Newfoundland and Labrador|"
    r"Nova Scotia|Ontario|Prince Edward Island|Quebec|Saskatchewan|"
    r"Northwest Territories|Nunavut|Yukon)"
)
_LOCATION_COMPANY_CANDIDATE = re.compile(
    rf"^[A-Za-z.' -]{{2,80}},\s*"
    rf"(?:(?:{_STATE_OR_PROVINCE}),\s*)?"
    r"(?:United States(?: of America)?|USA|US|Canada)$",
    re.IGNORECASE,
)


def extract_posting_metadata_evidence(content: str) -> tuple[PostingMetadataEvidence, ...]:
    """Extract narrow high-confidence metadata not covered by the core parser yet."""
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return ()

    evidence: list[PostingMetadataEvidence] = []

    company = _AT_COMPANY.search(text)
    if company:
        value = " ".join(company.group("company").split()).strip(" ,.;:-")
        if value:
            evidence.append(
                PostingMetadataEvidence(
                    field="company",
                    value=value,
                    evidence=_context_line(text, company.start(), company.end()),
                    confidence=0.99,
                    rule="at_company_with_trademark",
                )
            )

    sponsorship = _SPONSORSHIP_ELIGIBILITY.search(text)
    if sponsorship:
        answer = sponsorship.group("answer").casefold()
        evidence.append(
            PostingMetadataEvidence(
                field="sponsorship",
                value="Available" if answer == "yes" else "Not offered",
                evidence=_context_line(text, sponsorship.start(), sponsorship.end()),
                confidence=1.0,
                rule="sponsorship_eligibility_answer",
            )
        )

    return tuple(evidence)


def is_location_like_company_candidate(value: str) -> bool:
    """Reject capture-level company candidates that are clearly posting geography."""
    text = " ".join(str(value).split()).strip(" ,.;:-")
    return bool(_LOCATION_COMPANY_CANDIDATE.fullmatch(text))


def _context_line(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    return " ".join(text[line_start:line_end].split())[:360]


__all__ = [
    "PostingMetadataEvidence",
    "extract_posting_metadata_evidence",
    "is_location_like_company_candidate",
]
