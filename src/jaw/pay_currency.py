from __future__ import annotations

import re


_CANADIAN_LOCATION = re.compile(
    r"\b[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,4},\s*"
    r"(?:Alberta|British Columbia|Manitoba|New Brunswick|Newfoundland and Labrador|"
    r"Nova Scotia|Ontario|Prince Edward Island|Quebec|Saskatchewan|"
    r"Northwest Territories|Nunavut|Yukon),\s*Canada\b",
    re.IGNORECASE,
)
_EXPLICIT_US = re.compile(r"\b(?:USD|U\.S\.\s+pay\s+range|US\s+pay\s+range)\b", re.IGNORECASE)
_EXPLICIT_CAD = re.compile(r"\bCAD\b", re.IGNORECASE)


def resolve_pay_currency(content: str, detected: str, evidence: str = "") -> str:
    """Resolve ambiguous dollar currency from strong posting geography.

    Explicit currency markers always win. A bare dollar sign is treated as CAD
    only when the posting header clearly places the role in Canada.
    """
    evidence_text = str(evidence)
    if _EXPLICIT_CAD.search(evidence_text):
        return "CAD"
    if _EXPLICIT_US.search(evidence_text):
        return "USD"

    detected = str(detected or "").upper()
    if detected not in {"", "USD"}:
        return detected

    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    header = text[:1200]
    if _CANADIAN_LOCATION.search(header) and not _EXPLICIT_US.search(header):
        return "CAD"
    return detected or "USD"


__all__ = ["resolve_pay_currency"]
