from __future__ import annotations

import re
from typing import Any

_REMOTE_WORK_BENEFIT = re.compile(
    r"\b(?:stipends?|allowances?|reimbursements?|budgets?|benefits?)\b"
    r"[^.\n]{0,90}\bremote\s+work\b|"
    r"\bremote\s+work\b[^.\n]{0,90}"
    r"\b(?:stipends?|allowances?|reimbursements?|budgets?|benefits?)\b",
    re.IGNORECASE,
)
_ONSITE_INTERVIEW = re.compile(
    r"\b(?:on[- ]?site|onsite|in[- ]person)\s+interview\b|"
    r"\binterview\b[^.\n]{0,100}\b(?:on[- ]?site|onsite|in[- ]person)\b",
    re.IGNORECASE,
)


def suppress_work_arrangement(analysis: Any) -> bool:
    """Suppress arrangement results that come only from non-workplace context.

    Remote-work benefits and onsite interview logistics can mention arrangement
    terms without describing where the employee actually performs the job. Mixed
    evidence is never suppressed; a genuine workplace statement still wins.
    """
    status = str(getattr(analysis, "status", ""))
    evidence = tuple(getattr(analysis, "evidence", ()) or ())
    if not evidence:
        return False

    if status == "Remote":
        remote_items = [
            item
            for item in evidence
            if str(getattr(item, "arrangement", "")) == "remote"
        ]
        if len(remote_items) != len(evidence):
            return False
        return all(
            _REMOTE_WORK_BENEFIT.search(str(getattr(item, "evidence", "")))
            for item in remote_items
        )

    if status == "On-site":
        onsite_items = [
            item
            for item in evidence
            if str(getattr(item, "arrangement", "")) == "on-site"
        ]
        if len(onsite_items) != len(evidence):
            return False
        return all(
            _ONSITE_INTERVIEW.search(str(getattr(item, "evidence", "")))
            for item in onsite_items
        )

    return False


__all__ = ["suppress_work_arrangement"]