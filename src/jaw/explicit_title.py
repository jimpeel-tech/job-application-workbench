from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExplicitTitle:
    value: str = ""
    rule: str = ""


_JOB_TITLE = re.compile(
    r"(?:^|\n)\s*Job\s+Title\s*:\s*(?P<value>[^\n]{2,160})",
    re.IGNORECASE,
)
_ROLE_TERM = re.compile(
    r"\b(?:administrator|analyst|architect|consultant|developer|director|engineer|"
    r"manager|officer|principal|scientist|specialist|technician|sre|devops|"
    r"devsecops|program\s+manager|product\s+manager)\b",
    re.IGNORECASE,
)
_COMPANY_LOGO = re.compile(r"^Company\s+logo\s+for,?\b", re.IGNORECASE)
_HEADER_METADATA = re.compile(
    r"(?:^|\n)\s*(?:"
    r"Remote\s*-\s*US\b|"
    r"Job\s+category\s*:|"
    r"Job\s+ID\s*:|"
    r"Category\b|"
    r"Posted\s+Date\b|"
    r"Job\s+available\s+in\b"
    r")",
    re.IGNORECASE,
)
_LOCATION_METADATA = re.compile(
    r"(?:^|\n)\s*[A-Z][A-Za-z .'-]+,\s*(?:"
    r"[A-Z]{2}|[A-Z][A-Za-z .'-]+"
    r")(?:,\s*(?:United States(?: of America)?|Canada))?\s*(?:·|$)",
)


def analyze_explicit_title(content: str) -> ExplicitTitle:
    """Return high-confidence title evidence from labeled or ATS-shaped headers.

    ``Job Title:`` is explicit evidence. Unlabeled headers are accepted only when
    their surrounding structure strongly identifies them as posting metadata; a
    bare first line followed by prose remains ordinary parser inference instead.
    """
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    match = _JOB_TITLE.search(text)
    if match:
        value = _clean(match.group("value"))
        if value:
            return ExplicitTitle(value=value, rule="explicit_job_title_label")

    header = _header_title(text)
    if header:
        return ExplicitTitle(value=header, rule="posting_header_title")
    return ExplicitTitle()


def _header_title(text: str) -> str:
    lines = [_clean(line) for line in text.splitlines()[:16] if _clean(line)]
    if not lines:
        return ""

    company_logo = bool(_COMPANY_LOGO.search(lines[0]))
    if company_logo:
        candidate = lines[2] if len(lines) >= 3 else ""
    else:
        candidate = lines[0]
        header_region = "\n".join(lines[:8])
        if not (
            _HEADER_METADATA.search(header_region)
            or _LOCATION_METADATA.search(header_region)
        ):
            return ""

    if not _valid_header_title(candidate):
        return ""
    return candidate


def _valid_header_title(value: str) -> bool:
    if not value or len(value) > 160 or not _ROLE_TERM.search(value):
        return False
    lowered = value.casefold()
    if any(
        marker in lowered
        for marker in ("company logo for", "about the job", "job description")
    ):
        return False
    if any(marker in value for marker in ("|", "·", "$")):
        return False
    return True


def _clean(value: str) -> str:
    return " ".join(str(value).split()).strip(" \t:;,.")


__all__ = ["ExplicitTitle", "analyze_explicit_title"]
