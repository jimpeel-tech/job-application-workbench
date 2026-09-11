from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExplicitClearance:
    value: str = ""
    rule: str = ""


_ENHANCED_RELIABILITY = re.compile(
    r"\bEnhanced\s+Reliability\s+Clearance\b",
    re.IGNORECASE,
)


def analyze_explicit_clearance(content: str) -> ExplicitClearance:
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    if _ENHANCED_RELIABILITY.search(text):
        return ExplicitClearance(
            value="Enhanced Reliability Clearance",
            rule="enhanced_reliability_clearance",
        )
    return ExplicitClearance()


__all__ = ["ExplicitClearance", "analyze_explicit_clearance"]
