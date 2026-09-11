from __future__ import annotations

import re

from .ats_location_evidence import analyze_ats_locations
from .work_arrangement import (
    WorkArrangementAnalysis,
    WorkArrangementEvidence,
    analyze_work_arrangement,
)

_WORK_ARRANGEMENT_ROW = re.compile(
    r"(?:^|\n)\s*Work\s+Arrangement\s*:\s*"
    r"(?P<value>Remote|Hybrid|On[- ]?site|Onsite|In[- ]office|In[- ]person)\b",
    re.IGNORECASE,
)
_WEEKDAY_HYBRID_POLICY = re.compile(
    r"\b(?:teams?|employees?)\b[^.\n]{0,120}\bwork\s+in\s+the\s+office\b"
    r"[^.\n]{0,120}\bMonday\s+through\s+Thursday\b[^\n]{0,220}"
    r"\bFridays?\b[^.\n]{0,120}\bremote\s+work\b",
    re.IGNORECASE,
)
_REMOTE_TERRITORY = re.compile(
    r"\bThis\s+is\s+a\s+remote\s+position\s*;?\s*however,?\s*"
    r"candidates?\s+must\s+be\s+based\s+in\s+"
    r"(?P<locations>[^.\n]{2,140}?)"
    r"(?=\s+to\s+(?:effectively\s+)?support\b|[.;\n])",
    re.IGNORECASE,
)
_REMOTE_US_MULTI = re.compile(
    r"(?mi)^\s*Remote\s*-\s*(?:US|USA)\s*;\s*United\s+States\s*;[^\n]+$"
)
_METADATA_LABEL_LEAK = re.compile(
    r"\b(?:Work\s+Arrangement|Employment\s+Type|Compensation|Benefits|Job\s+Summary)\b",
    re.IGNORECASE,
)
_STATE_ALIASES = {
    "louisianna": "Louisiana",
}


def analyze_enriched_work_arrangement(content: str) -> WorkArrangementAnalysis:
    """Add narrow high-confidence workplace evidence on top of the core analyzer."""
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    base = analyze_work_arrangement(text)
    evidence = [
        item
        for item in base.evidence
        if not (
            item.rule == "location_row_arrangement"
            and item.location
            and _METADATA_LABEL_LEAK.search(item.location)
        )
    ]

    posting_locations = analyze_ats_locations(text)
    posting_location = posting_locations[0].value if posting_locations else ""

    row = _WORK_ARRANGEMENT_ROW.search(text)
    if row:
        arrangement = _canonical(row.group("value"))
        if arrangement:
            evidence.append(
                WorkArrangementEvidence(
                    arrangement=arrangement,
                    value=_label(arrangement),
                    evidence=" ".join(row.group(0).split()),
                    location=posting_location,
                    location_relation="posting_location" if posting_location else "unknown",
                    confidence=0.995,
                    rule="explicit_work_arrangement_label",
                )
            )

    weekday = _WEEKDAY_HYBRID_POLICY.search(text)
    if weekday:
        evidence.append(
            WorkArrangementEvidence(
                arrangement="hybrid",
                value="Hybrid",
                evidence=" ".join(weekday.group(0).split())[:360],
                confidence=0.97,
                rule="weekday_hybrid_policy",
            )
        )

    territory = _REMOTE_TERRITORY.search(text)
    if territory:
        # In an explicitly remote role, a state list following "must be based in"
        # describes the geography in which remote work is eligible. Replace the
        # core analyzer's collapsed residence candidate with per-state evidence.
        evidence = [
            item
            for item in evidence
            if item.location_relation != "residence_requirement"
        ]
        clause = " ".join(territory.group(0).split())[:360]
        for location in _split_territory_locations(territory.group("locations")):
            evidence.append(
                WorkArrangementEvidence(
                    arrangement="remote",
                    value="Remote",
                    evidence=clause,
                    location=location,
                    location_relation="remote_eligibility",
                    confidence=0.995,
                    rule="explicit_remote_territory",
                )
            )

    multi = _REMOTE_US_MULTI.search(text)
    if multi:
        # The core metadata rule treats the entire semicolon-delimited header as
        # one location. Keep Remote status, but replace that collapsed geography
        # with a clean country-level eligibility fact. ATS location extraction
        # retains the individual posting locations separately.
        evidence = [
            item
            for item in evidence
            if not (
                item.arrangement == "remote"
                and item.location
                and ";" in item.location
            )
        ]
        evidence.append(
            WorkArrangementEvidence(
                arrangement="remote",
                value="Remote",
                evidence=" ".join(multi.group(0).split())[:360],
                location="United States",
                location_relation="remote_eligibility",
                confidence=0.995,
                rule="remote_us_multilocation_header",
            )
        )

    evidence = _dedupe(evidence)
    status, conflict = _resolve(evidence)
    return WorkArrangementAnalysis(
        status=status,
        location=_primary_location(evidence),
        evidence=tuple(evidence),
        conflict=conflict,
    )


def _canonical(value: str) -> str:
    lowered = " ".join(str(value).casefold().split())
    if "remote" in lowered:
        return "remote"
    if "hybrid" in lowered:
        return "hybrid"
    return "on-site"


def _label(arrangement: str) -> str:
    return {
        "remote": "Remote",
        "hybrid": "Hybrid",
        "on-site": "On-site",
        "telework": "Telework eligible",
        "field-based": "Field-based",
        "flexible": "Flexible",
    }.get(arrangement, arrangement)


def _split_territory_locations(value: str) -> tuple[str, ...]:
    raw = re.sub(r"\s+or\s+", ",", str(value), flags=re.IGNORECASE)
    parts = [" ".join(part.split()).strip(" ,;.") for part in raw.split(",")]
    result: list[str] = []
    for part in parts:
        if not part:
            continue
        normalized = _STATE_ALIASES.get(part.casefold(), part.title())
        if normalized.casefold() not in {item.casefold() for item in result}:
            result.append(normalized)
    return tuple(result)


def _dedupe(items: list[WorkArrangementEvidence]) -> list[WorkArrangementEvidence]:
    result: list[WorkArrangementEvidence] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        key = (
            item.arrangement,
            item.evidence.casefold(),
            item.location.casefold(),
            item.location_relation,
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _resolve(evidence: list[WorkArrangementEvidence]) -> tuple[str, bool]:
    arrangements = {item.arrangement for item in evidence}
    if "remote" in arrangements and "on-site" in arrangements:
        return "Conflicting remote claim", True
    if "hybrid" in arrangements:
        return "Hybrid", False
    if "remote" in arrangements:
        return "Remote", False
    if "on-site" in arrangements:
        return "On-site", False
    if "flexible" in arrangements:
        return "Flexible", False
    if "telework" in arrangements:
        strongest = max(
            (item for item in evidence if item.arrangement == "telework"),
            key=lambda item: item.confidence,
        )
        return strongest.value, False
    if "field-based" in arrangements:
        return "Field-based", False
    return "", False


def _primary_location(evidence: list[WorkArrangementEvidence]) -> str:
    # A semicolon-delimited remote header can encode scope plus several posting
    # locations. There is no truthful single primary location in that shape;
    # leave the scalar empty so the ATS layer can retain all explicit locations.
    if any(item.rule == "remote_us_multilocation_header" for item in evidence):
        return ""

    candidates = [item for item in evidence if item.location and item.location_relation != "unknown"]
    if not candidates:
        return ""
    priority = {
        "office_location": 4,
        "residence_requirement": 3,
        "remote_eligibility": 2,
        "posting_location": 1,
    }
    candidates.sort(
        key=lambda item: (priority.get(item.location_relation, 0), item.confidence),
        reverse=True,
    )

    highest = priority.get(candidates[0].location_relation, 0)
    peers = [
        item
        for item in candidates
        if priority.get(item.location_relation, 0) == highest
    ]
    distinct = {item.location.casefold() for item in peers}
    if len(distinct) > 1:
        return ""
    return candidates[0].location


__all__ = ["analyze_enriched_work_arrangement"]
