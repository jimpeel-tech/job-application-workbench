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


def analyze_enriched_work_arrangement(content: str) -> WorkArrangementAnalysis:
    """Add narrow high-confidence workplace evidence on top of the core analyzer."""
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    base = analyze_work_arrangement(text)
    evidence = list(base.evidence)

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
    return candidates[0].location


__all__ = ["analyze_enriched_work_arrangement"]
