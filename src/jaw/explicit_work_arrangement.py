from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExplicitWorkArrangement:
    status: str = ""
    location: str = ""
    rule: str = ""


_TECHNICAL_REMOTE = re.compile(
    r"\bremote\s+(?:access|desktop|support|monitoring|server|shell|command|"
    r"connection|endpoint|debugging|repair|repairs)\b",
    re.IGNORECASE,
)
_TECHNICAL_HYBRID = re.compile(
    r"\bhybrid\s+(?:cloud|infrastructure|environment|architecture|network|"
    r"deployment|system|systems|platform|engineering|operations|technical)\b",
    re.IGNORECASE,
)
_LOCATION_ROW = re.compile(
    r"^\s*(?:(?:job|work)\s+)?location\s*:\s*(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_REMOTE_SCOPE_US = re.compile(
    r"\b(?:remote(?:ly)?|remote\s+role)\b[^.\n]{0,80}\b"
    r"(?:within|in|throughout|based\s+in)\s+(?:the\s+)?"
    r"(?:U\.?S\.?A?\.?|United States(?: of America)?)\b",
    re.IGNORECASE,
)
_REMOTE_COUNTRY_SCOPE = re.compile(
    r"\bremote\s*\(\s*(?:US|U\.S\.?|USA|U\.S\.A\.?|United States)"
    r"(?:\s*/\s*Canada)?\s*\)",
    re.IGNORECASE,
)


def analyze_explicit_work_arrangement(content: str) -> ExplicitWorkArrangement:
    """Extract only high-confidence workplace signals missed by the richer analyzer.

    This is intentionally conservative and is used only as a fallback when the
    primary work-arrangement analyzer does not resolve a status or location.
    """
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return ExplicitWorkArrangement()

    lines = [" ".join(line.split()).strip() for line in text.splitlines() if line.strip()]

    for line in lines:
        row = _LOCATION_ROW.fullmatch(line)
        if not row:
            continue
        body = row.group("body").strip()
        lowered = body.casefold()
        normalized = re.sub(r"\s*-\s*", "-", lowered)
        if re.search(r"\b(?:customer|client)[- ]site\b", normalized):
            return ExplicitWorkArrangement("On-site", "", "work_location_customer_site")
        if re.search(r"\b(?:on[- ]?site|onsite|in[- ]person|in[- ]office)\b", normalized):
            return ExplicitWorkArrangement("On-site", "", "work_location_on_site")
        if re.search(r"\b(?:home[- ]based|fully\s+remote|remote)\b", normalized):
            return ExplicitWorkArrangement("Remote", _remote_location(body), "work_location_remote")
        if re.fullmatch(r"(?:US,\s*)?Virtual(?:,\s*NOAM)?", body, re.IGNORECASE):
            return ExplicitWorkArrangement("Remote", "", "work_location_virtual")

    for line in lines:
        if len(line) > 160 or _TECHNICAL_REMOTE.search(line) or _TECHNICAL_HYBRID.search(line):
            continue
        lowered = line.casefold()
        if re.match(r"^\s*(?:hybrid\s*/\s*remote|remote\s*/\s*hybrid)\b", line, re.IGNORECASE):
            return ExplicitWorkArrangement("Hybrid", "", "compact_hybrid_remote_badge")
        if re.fullmatch(r"(?:fully\s+)?remote", line, re.IGNORECASE):
            return ExplicitWorkArrangement("Remote", "", "standalone_remote_badge")
        if re.fullmatch(r"hybrid", line, re.IGNORECASE):
            return ExplicitWorkArrangement("Hybrid", "", "standalone_hybrid_badge")
        if re.fullmatch(r"(?:on[- ]?site|onsite|in[- ]person)", line, re.IGNORECASE):
            return ExplicitWorkArrangement("On-site", "", "standalone_on_site_badge")
        if re.fullmatch(r"home[- ]based(?:,\s*.+)?", line, re.IGNORECASE):
            return ExplicitWorkArrangement("Remote", _home_based_location(line), "standalone_home_based")
        if _REMOTE_COUNTRY_SCOPE.search(line):
            return ExplicitWorkArrangement("Remote", "", "remote_country_scope")
        if re.search(r"\(\s*remote\s*\)\s*$", line, re.IGNORECASE):
            return ExplicitWorkArrangement("Remote", "", "title_remote_suffix")
        if re.search(r"(?:^|\s[-–—|]\s)remote\s*$", line, re.IGNORECASE):
            return ExplicitWorkArrangement("Remote", "", "title_remote_suffix")
        if "remote first" in lowered and "remote always" in lowered:
            return ExplicitWorkArrangement("Remote", "", "remote_first_badge")
        if re.search(r"(?:^|\s)#LI-REMOTE\b", line, re.IGNORECASE):
            return ExplicitWorkArrangement("Remote", "", "li_remote_tag")

    prose_patterns = (
        (r"\b(?:100%|fully)\s+remote\b", "Remote", "explicit_remote_prose"),
        (r"\bremote\s+(?:US|U\.S\.)\s+workforce\b", "Remote", "remote_workforce"),
        (r"\bexpand(?:ing)?\s+(?:our\s+)?remote\s+(?:US|U\.S\.)\s+workforce\b", "Remote", "remote_workforce"),
        (r"\bremote\s+work\s+(?:is\s+)?(?:allowed|available|offered|supported)\b", "Remote", "remote_work_allowed"),
        (r"\bwork(?:ing)?\s+remotely\b", "Remote", "working_remotely"),
        (r"\bhome[- ]based\b", "Remote", "home_based_prose"),
        (
            r"\bremote[- ]first\b[^.\n]{0,60}\b(?:company|culture|team|work\s+culture)\b",
            "Remote",
            "remote_first_culture",
        ),
        (
            r"\bvirtual[- ]first\b[^.\n]{0,60}\b(?:company|culture|team|work\s+culture)\b",
            "Remote",
            "virtual_first_culture",
        ),
        (r"\bin[- ]office\s+role\b", "On-site", "in_office_role"),
        (r"\bteam\s+works?\s+in[- ]person\b", "On-site", "team_works_in_person"),
    )
    for pattern, status, rule in prose_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        clause = _line_for_match(text, match.start(), match.end())
        if _TECHNICAL_REMOTE.search(clause) or _TECHNICAL_HYBRID.search(clause):
            continue
        location = "United States" if status == "Remote" and _REMOTE_SCOPE_US.search(clause) else ""
        return ExplicitWorkArrangement(status, location, rule)

    return ExplicitWorkArrangement()


def _remote_location(body: str) -> str:
    if re.search(r"\b(?:U\.?S\.?A?\.?|United States(?: of America)?)\b", body, re.IGNORECASE):
        return "United States"
    return ""


def _home_based_location(value: str) -> str:
    match = re.search(r"home[- ]based\s*,\s*(?P<location>[^;|]+)$", value, re.IGNORECASE)
    return " ".join(match.group("location").split()).strip(" ,") if match else ""


def _line_for_match(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    return " ".join(text[line_start:line_end].split())[:360]


__all__ = ["ExplicitWorkArrangement", "analyze_explicit_work_arrangement"]
