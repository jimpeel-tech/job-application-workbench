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
    """Return only titles that are explicitly labeled in the posting text.

    Generic header/title inference belongs to the normal combined parser layer.
    Keeping this analyzer label-only prevents synthetic whole-text evidence from
    outranking a real ``job_title`` capture while still allowing high-confidence
    ATS labels such as ``Job Title: Machine Learning Engineer`` to win.
    """
    text = str(content).replace("\r\n", "\n").replace("\r", "\n")
    match = _JOB_TITLE.search(text)
    if not match:
        return ExplicitTitle()

    value = _clean(match.group("value"))
    if not value:
        return ExplicitTitle()
    return ExplicitTitle(value=value, rule="explicit_job_title_label")


def _clean(value: str) -> str:
    return " ".join(str(value).split()).strip(" \t:;,.")


__all__ = ["ExplicitTitle", "analyze_explicit_title"]
