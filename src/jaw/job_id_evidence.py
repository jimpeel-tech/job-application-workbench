from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class JobIdEvidence:
    value: str = ""
    evidence: str = ""
    confidence: float = 0.0
    rule: str = ""


_LABELED_ID = re.compile(
    r"(?:^|\n)\s*(?:Job\s+Code|Ref\.?\s*(?:code|ID)|Job\s+ID|Requisition\s+ID)\s*:?\s*"
    r"(?:\n\s*)?(?P<value>[A-Z0-9][A-Z0-9._/-]{2,40})\b",
    re.IGNORECASE,
)
_ATS_COLLAPSED_ID = re.compile(
    r"(?:Job\s+Id|Ref\s+ID)\s*:?\s*(?:\n\s*)?"
    r"(?P<value>(?:[A-Z]{1,4}-?)?\d{4,12})"
    r"(?=Posted\s+Date|\s|$)",
    re.IGNORECASE,
)
_INLINE_ID = re.compile(
    r"\bID\s*:\s*(?P<value>\d{4,10})\b",
    re.IGNORECASE,
)
_STANDALONE_NUMERIC_ID = re.compile(r"(?m)^\s*(?P<value>\d{4,10})\s*$")


def analyze_job_id(content: str) -> JobIdEvidence:
    """Extract high-confidence job identifiers missed by the legacy parser."""
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return JobIdEvidence()

    labeled = _LABELED_ID.search(text)
    if labeled:
        return JobIdEvidence(
            value=labeled.group("value"),
            evidence=_line_for_match(text, labeled.start(), labeled.end()),
            confidence=1.0,
            rule="explicit_job_id_label",
        )

    ats = _ATS_COLLAPSED_ID.search(text)
    if ats:
        return JobIdEvidence(
            value=ats.group("value"),
            evidence=_line_for_match(text, ats.start(), ats.end()),
            confidence=0.995,
            rule="ats_job_id_label",
        )

    inline = _INLINE_ID.search(text)
    if inline:
        return JobIdEvidence(
            value=inline.group("value"),
            evidence=_line_for_match(text, inline.start(), inline.end()),
            confidence=0.99,
            rule="inline_job_id",
        )

    standalone = [
        match.group("value")
        for match in _STANDALONE_NUMERIC_ID.finditer(text)
        if not _looks_like_year(match.group("value"))
    ]
    repeated = [
        value
        for value, count in Counter(standalone).items()
        if count >= 2
    ]
    if len(repeated) == 1:
        value = repeated[0]
        return JobIdEvidence(
            value=value,
            evidence=value,
            confidence=0.97,
            rule="repeated_standalone_job_id",
        )

    return JobIdEvidence()


def _looks_like_year(value: str) -> bool:
    if len(value) != 4:
        return False
    year = int(value)
    return 1900 <= year <= 2100


def _line_for_match(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    return " ".join(text[line_start:line_end].split())[:240]


__all__ = ["JobIdEvidence", "analyze_job_id"]
