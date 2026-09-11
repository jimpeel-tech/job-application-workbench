"""Private, deterministic capability analysis provider."""

from __future__ import annotations

from typing import Any

from ...config import RATING_GUIDANCE, AppConfig
from ..contracts import AnalysisRequest
from ..graph_matching import (
    local_capability_score,
    mentioned_capabilities,
    transfer_candidates,
)
from ..normalization import normalize_remote_status, normalize_result, number


class DeterministicAnalysisProvider:
    """Fast, private local rules. This is not the future local LLM provider."""

    name = "local"

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @property
    def available(self) -> bool:
        return True

    def test_connection(self) -> str:
        return "Local Analyzer is ready"

    def analyze(
        self,
        request: AnalysisRequest,
    ) -> tuple[dict[str, Any], str]:
        extracted = dict(request.extracted_job.get("fields", {}))
        mentioned = mentioned_capabilities(self.config, request.description)

        strong_matches: list[str] = []
        concerns: list[str] = []
        missing: list[str] = []

        for capability in mentioned:
            if capability.rating >= 3:
                strong_matches.append(f"{capability.name} ({capability.rating}/5)")
                continue

            if capability.rating in {1, 2}:
                guidance = RATING_GUIDANCE[capability.rating]
                concerns.append(
                    f"{capability.name} is mentioned in the job; "
                    f"candidate rating is {capability.rating}/5 "
                    f"({guidance['label']} — {guidance['description']})."
                )
                continue

            transfer = transfer_candidates(self.config, capability)
            concerns.append(
                f"{capability.name} is mentioned in the job, but its JAW "
                "rating is 0/5 (Unrated). Treat proficiency as unassessed, "
                "not as evidence that the candidate lacks the capability."
            )
            if transfer:
                for _weight, relationship_path, neighbor in transfer[:3]:
                    path_label = " / ".join(relationship_path)
                    concerns.append(
                        f"{capability.name} is unassessed; {neighbor.name} is rated "
                        f"{neighbor.rating}/5 and is connected through {path_label}. "
                        "This may indicate transferable experience, but does not "
                        "establish a proficiency level for the unrated capability."
                    )

        required_items = [
            str(item)
            for item in extracted.get("required_skills", [])
            if str(item).strip()
        ]
        if required_items and not mentioned:
            concerns.extend(
                f"Review explicit requirement: {item}" for item in required_items[:3]
            )

        required_certifications = [
            str(item)
            for item in extracted.get("required_certifications", [])
            if str(item).strip()
        ]
        concerns.extend(
            f"Verify certification/clearance requirement: {item}"
            for item in required_certifications[:3]
        )

        pay_min = number(extracted.get("pay_min"))
        pay_max = number(extracted.get("pay_max"))

        result = {
            "company": extracted.get("company", ""),
            "title": extracted.get("title", ""),
            "location": extracted.get("location", ""),
            "remote_status": normalize_remote_status(
                extracted.get("remote_status", "")
            ),
            "pay_min": pay_min,
            "pay_max": pay_max,
            "currency": extracted.get("currency", ""),
            "pay_period": extracted.get("pay_period", ""),
            "pay_disclosed": pay_min is not None or pay_max is not None,
            "match_score": local_capability_score(self.config, mentioned),
            "summary": (
                "Local rule-based analysis found "
                f"{sum(capability.rating >= 3 for capability in mentioned)} "
                "direct capability match(es) across "
                f"{len(mentioned)} catalog capability mention(s). "
                "The score does not use semantic model inference."
            ),
            "strong_matches": strong_matches,
            "concerns": concerns,
            "missing_qualifications": missing,
        }
        return normalize_result(result), self.name
