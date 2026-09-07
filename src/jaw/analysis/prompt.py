"""Shared prompts for generative job-analysis providers."""

from __future__ import annotations

import json
from typing import Any

from .contracts import AnalysisRequest

SYSTEM_PROMPT = (
    "Analyze a job description against the supplied candidate capability graph "
    "and work history. Use only evidence in the candidate snapshot and job "
    "description. Capability ratings are authoritative and use the supplied "
    "rating_scale definitions. A rating of 0 means Unrated: no proficiency level "
    "has been assigned, and it does not mean no knowledge. Do not count a 0-rated "
    "capability as a direct rated match, but do not call it missing solely because "
    "it is unrated; describe it as unassessed when relevant. Interpret ratings "
    "1-5 exactly according to the supplied scale; do not inflate conceptual or "
    "narrow hands-on experience into production proficiency. Aliases "
    "are only alternate names. Semantic relationships such as based_on, uses, and "
    "related_to may justify transferability, but they do not establish a "
    "proficiency level for another capability. Distinguish explicit requirements "
    "from preferences. Missing qualifications must contain only unmet explicit "
    "requirements, never preferred or bonus qualifications. Strong matches, "
    "concerns, and missing qualifications must use concise human-readable names "
    "and explanations, never internal capability IDs. Match score is a comparative "
    "job-fit heuristic, not a "
    "hiring probability. Extract employer, title, location, work arrangement, and "
    "compensation only when supported by the posting. Do not invent qualifications."
)


def build_analysis_messages(request: AnalysisRequest) -> list[dict[str, Any]]:
    """Build provider-neutral chat messages for job analysis."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Candidate snapshot:\n"
                f"{json.dumps(request.candidate, ensure_ascii=False)}\n\n"
                "Deterministic extraction hints (may be incomplete; the job "
                "description remains the source of truth):\n"
                f"{json.dumps(request.extracted_job, ensure_ascii=False)}\n\n"
                "Job description:\n"
                f"{request.description}"
            ),
        },
    ]
