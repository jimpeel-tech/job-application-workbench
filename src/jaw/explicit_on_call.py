from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExplicitOnCall:
    value: str = ""
    evidence: str = ""
    rule: str = ""


_PARTICIPATES_IN_SHIFTS = re.compile(
    r"\bparticipat(?:e|es|ing)\b[^.\n]{0,60}\bon[- ]call\s+shifts?\b",
    re.IGNORECASE,
)
_PART_OF_ROTATION = re.compile(
    r"\b(?:will\s+be|is|are|be)\s+part\s+of\s+(?:an?\s+)?on[- ]call\s+rotation\b",
    re.IGNORECASE,
)


def analyze_explicit_on_call(content: str) -> ExplicitOnCall:
    """Capture narrow explicit on-call wording missed by the general evidence layer."""
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    for pattern, rule in (
        (_PARTICIPATES_IN_SHIFTS, "participates_on_call_shifts"),
        (_PART_OF_ROTATION, "part_of_on_call_rotation"),
    ):
        match = pattern.search(text)
        if match:
            return ExplicitOnCall(
                value="Required",
                evidence=_line_for_match(text, match.start(), match.end()),
                rule=rule,
            )
    return ExplicitOnCall()


def _line_for_match(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    return " ".join(text[line_start:line_end].split())[:240]


__all__ = ["ExplicitOnCall", "analyze_explicit_on_call"]
