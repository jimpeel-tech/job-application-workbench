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


def suppress_work_arrangement(analysis: Any) -> bool:
    """Suppress a Remote result when its only evidence is a remote-work benefit.

    This intentionally does not suppress mixed evidence. A genuine role/workplace
    statement elsewhere in the posting should still classify the job as Remote.
    """
    if str(getattr(analysis, "status", "")) != "Remote":
        return False

    evidence = tuple(getattr(analysis, "evidence", ()) or ())
    if not evidence:
        return False

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


__all__ = ["suppress_work_arrangement"]
