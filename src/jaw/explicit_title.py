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


def analyze_explicit_title(content: str) -> ExplicitTitle:
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    match = _JOB_TITLE.search(text)
    if not match:
        return ExplicitTitle()
    value = " ".join(match.group("value").split()).strip(" \t:;,.")
    return ExplicitTitle(value=value, rule="explicit_job_title_label") if value else ExplicitTitle()


__all__ = ["ExplicitTitle", "analyze_explicit_title"]
