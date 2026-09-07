from dataclasses import replace
from typing import Any

import pytest

from jaw.analysis.context import build_analysis_request
from jaw.analysis.contracts import AnalysisRequest
from jaw.analysis.normalization import normalize_result
from jaw.analysis.providers.openai import build_openai_request_body
from jaw.analysis.schema import JOB_SCHEMA
from jaw.analyzer import (
    JobAnalyzer,
    _normalize_result,
    candidate_context_data,
)
from jaw.config import (
    AppConfig,
    CapabilityEntry,
    RelationshipEntry,
    WorkEntry,
)


class StubProvider:
    name = "stub"

    def __init__(self) -> None:
        self.requests: list[AnalysisRequest] = []

    @property
    def available(self) -> bool:
        return True

    def test_connection(self) -> str:
        return "Stub is ready"

    def analyze(
        self,
        request: AnalysisRequest,
    ) -> tuple[dict[str, Any], str]:
        self.requests.append(request)
        return {
            "company": " Example ",
            "title": "Engineer",
            "remote_status": "fully remote",
            "pay_min": "200,000",
            "pay_max": "150000",
            "match_score": 110,
            "strong_matches": ["Kubernetes", "kubernetes"],
        }, "stub-model"


def _capability(
    capability_id: str,
    name: str,
    rating: int,
    *,
    entity_type: str = "product",
    match_enabled: bool = True,
) -> CapabilityEntry:
    return CapabilityEntry(
        id=capability_id,
        type=entity_type,
        canonical_name=name,
        display_name=name,
        rating=rating,
        match_enabled=match_enabled,
    )


def test_relationships_supply_transferable_evidence_without_rating_inflation():
    kubernetes = _capability(
        "cap-kubernetes", "Kubernetes", 4, entity_type="technology"
    )
    oke = _capability("cap-oke", "Oracle Kubernetes Engine", 4)
    eks = _capability("cap-eks", "Amazon EKS", 0)
    config = AppConfig(
        capabilities=[kubernetes, oke, eks],
        relationships=[
            RelationshipEntry(eks.id, "based_on", kubernetes.id),
            RelationshipEntry(oke.id, "based_on", kubernetes.id),
        ],
        analysis_mode="local",
    )

    result, source = JobAnalyzer(config).analyze(
        "Platform role\nRequirements\nProduction experience with Amazon EKS."
    )

    assert source == "local"
    assert result["strong_matches"] == []
    assert any(
        "Amazon EKS" in concern and "Unrated" in concern
        for concern in result["concerns"]
    )
    transfer = [
        concern
        for concern in result["concerns"]
        if "transferable experience" in concern
    ]
    assert any("Kubernetes is rated 4/5" in concern for concern in transfer)
    assert any(
        "Oracle Kubernetes Engine is rated 4/5" in concern
        for concern in transfer
    )
    assert all("Amazon EKS is rated 4/5" not in concern for concern in transfer)

    context = candidate_context_data(config)
    ratings = {
        capability["name"]: capability["rating"]
        for capability in context["capabilities"]
    }
    assert ratings["Amazon EKS"] == 0


def test_match_disabled_related_capability_is_not_used_as_evidence():
    kubernetes = _capability(
        "cap-kubernetes",
        "Kubernetes",
        5,
        entity_type="technology",
        match_enabled=False,
    )
    eks = _capability("cap-eks", "Amazon EKS", 0)
    config = AppConfig(
        capabilities=[kubernetes, eks],
        relationships=[
            RelationshipEntry(eks.id, "based_on", kubernetes.id),
        ],
        analysis_mode="local",
    )

    result, _source = JobAnalyzer(config).analyze(
        "Requirements\nProduction experience with Amazon EKS."
    )

    assert not any(
        "Kubernetes is rated" in concern
        for concern in result["concerns"]
    )


def test_analysis_request_builds_provider_neutral_candidate_and_job_context(
    monkeypatch: pytest.MonkeyPatch,
):
    kubernetes = _capability("cap-kubernetes", "Kubernetes", 4)
    disabled = _capability(
        "cap-disabled",
        "Disabled capability",
        5,
        match_enabled=False,
    )
    config = AppConfig(
        capabilities=[kubernetes, disabled],
        relationships=[
            RelationshipEntry(kubernetes.id, "related_to", disabled.id),
        ],
        work_history=[
            WorkEntry("SRE", "Example", "2020", "2024", "Operated clusters"),
            WorkEntry(
                "Hidden",
                "Example",
                "2019",
                "2020",
                enabled=False,
            ),
        ],
    )
    extraction = {"fields": {"title": "Platform Engineer"}}
    monkeypatch.setattr(
        "jaw.analysis.context.extract_job_fields",
        lambda _description: extraction,
    )

    request = build_analysis_request(config, "A Kubernetes role")

    assert request.description == "A Kubernetes role"
    assert request.extracted_job is extraction
    assert [item["id"] for item in request.candidate["capabilities"]] == [
        kubernetes.id
    ]
    assert request.candidate["relationships"] == [
        {
            "source_id": kubernetes.id,
            "source": kubernetes.name,
            "type": "related_to",
            "target_id": disabled.id,
            "target": disabled.name,
        }
    ]
    assert request.candidate["work_history"] == [
        {
            "title": "SRE",
            "company": "Example",
            "start": "2020",
            "end": "2024",
            "highlights": "Operated clusters",
        }
    ]


def test_candidate_context_uses_canonical_capability_rating_rubric():
    scale = candidate_context_data(AppConfig())["rating_scale"]

    assert scale == {
        "0": {"label": "Unrated", "description": "Not assessed"},
        "1": {
            "label": "Conceptual",
            "description": (
                "Understand the concepts/use cases; little or no hands-on experience"
            ),
        },
        "2": {
            "label": "Hands-on",
            "description": (
                "Have actually used it, but experience is limited or narrow"
            ),
        },
        "3": {
            "label": "Proficient",
            "description": "Can work independently on normal production tasks",
        },
        "4": {
            "label": "Advanced",
            "description": (
                "Deep experience; handles complex design/troubleshooting and can "
                "guide others"
            ),
        },
        "5": {
            "label": "Expert",
            "description": (
                "Extensive depth and breadth; regularly solves ambiguous/novel "
                "problems and can serve as a technical authority"
            ),
        },
    }


def test_job_analyzer_selects_local_and_registered_providers():
    local_config = AppConfig(
        analysis_mode="local",
        analysis_provider="stub",
    )
    analyzer = JobAnalyzer(local_config)
    stub = StubProvider()
    analyzer.register_provider("  STUB  ", stub)

    assert analyzer.test_connection() == "Local Analyzer is ready"
    assert analyzer.api_available
    assert not analyzer.uses_generative_ai

    analyzer.configure(
        replace(
            local_config,
            analysis_mode="generative",
            analysis_provider="stub",
        )
    )
    assert analyzer.test_connection() == "Stub is ready"
    result, source = analyzer.analyze("A remote engineering role")

    assert analyzer.uses_generative_ai
    assert analyzer.api_available
    assert source == "stub-model"
    assert len(stub.requests) == 1
    assert stub.requests[0].description == "A remote engineering role"
    # Provider output still crosses the common normalization boundary.
    assert result["company"] == "Example"
    assert result["pay_min"] == 150000.0
    assert result["pay_max"] == 200000.0
    assert result["match_score"] == 100
    assert result["strong_matches"] == ["Kubernetes"]


def test_job_analyzer_rejects_blank_and_unknown_custom_providers():
    analyzer = JobAnalyzer(
        AppConfig(
            analysis_mode="generative",
            analysis_provider="missing",
        )
    )

    with pytest.raises(ValueError, match="Provider name is required"):
        analyzer.register_provider(" ", StubProvider())
    assert not analyzer.api_available
    with pytest.raises(RuntimeError, match="Unsupported analysis provider: missing"):
        analyzer.test_connection()


def test_result_normalization_preserves_dashboard_contract():
    raw = {
        "company": " Example Corp ",
        "title": " SRE ",
        "remote_status": "telework eligible",
        "pay_min": "220,000",
        "pay_max": "180000",
        "pay_disclosed": False,
        "match_score": "-8",
        "strong_matches": [" Kubernetes ", "kubernetes", ""],
        "concerns": ["On call", "ON CALL"],
        "missing_qualifications": ["Certification"],
    }

    result = normalize_result(raw)

    assert result == _normalize_result(raw)
    assert result["company"] == "Example Corp"
    assert result["title"] == "SRE"
    assert result["remote_status"] == "Hybrid"
    assert result["pay_min"] == 180000.0
    assert result["pay_max"] == 220000.0
    assert result["pay_disclosed"]
    assert result["match_score"] == 0
    assert result["strong_matches"] == ["Kubernetes"]
    assert result["concerns"] == ["On call"]


def test_openai_request_body_uses_shared_schema_and_complete_request_context():
    request = AnalysisRequest(
        description="Senior SRE with Kubernetes",
        candidate={
            "capabilities": [{"id": "cap-k8s", "name": "Kubernetes", "rating": 4}],
            "relationships": [],
        },
        extracted_job={"fields": {"remote_status": "Remote"}},
    )

    body = build_openai_request_body("gpt-test", request)

    assert body["model"] == "gpt-test"
    assert body["store"] is False
    assert body["text"]["format"] == {
        "type": "json_schema",
        "name": "job_analysis",
        "strict": True,
        "schema": JOB_SCHEMA,
    }
    assert [message["role"] for message in body["input"]] == ["system", "user"]
    user_content = body["input"][1]["content"]
    assert '"name": "Kubernetes"' in user_content
    assert '"remote_status": "Remote"' in user_content
    assert user_content.endswith("Senior SRE with Kubernetes")
