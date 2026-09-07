from __future__ import annotations

import io
import json
from typing import Any

import pytest

from jaw.analysis.contracts import AnalysisRequest
from jaw.analysis.providers.ollama import (
    OllamaAnalysisProvider,
    build_ollama_request_body,
)
from jaw.analysis.schema import JOB_SCHEMA
from jaw.analysis.service import JobAnalyzer
from jaw.config import AppConfig


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _response(payload: dict[str, Any]) -> FakeResponse:
    return FakeResponse(json.dumps(payload).encode("utf-8"))


def _request() -> AnalysisRequest:
    return AnalysisRequest(
        description="Remote SRE role using Kubernetes",
        candidate={"capabilities": [{"name": "Kubernetes", "rating": 4}]},
        extracted_job={"fields": {"remote_status": "Remote"}},
    )


def test_ollama_request_uses_shared_schema_and_local_generation_options():
    body = build_ollama_request_body("qwen3:14b", _request())

    assert body["model"] == "qwen3:14b"
    assert body["format"] == JOB_SCHEMA
    assert body["stream"] is False
    assert body["think"] is False
    assert body["options"]["temperature"] == 0
    assert body["options"]["num_ctx"] == 8192
    assert [message["role"] for message in body["messages"]] == ["system", "user"]
    assert '"name": "Kubernetes"' in body["messages"][1]["content"]


def test_ollama_lists_models_and_tests_selected_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: _response(
            {"models": [{"name": "qwen3:14b"}, {"model": "gemma3:12b"}]}
        ),
    )
    provider = OllamaAnalysisProvider("qwen3:14b")

    assert provider.list_models() == ["qwen3:14b", "gemma3:12b"]
    assert provider.available
    assert provider.test_connection() == "Connected to Ollama · qwen3:14b"


def test_ollama_analyzes_and_normalizes_structured_response(
    monkeypatch: pytest.MonkeyPatch,
):
    result = {
        "company": " Example ",
        "title": "SRE",
        "location": "",
        "remote_status": "Remote",
        "pay_min": 200000,
        "pay_max": 150000,
        "currency": "USD",
        "pay_period": "year",
        "pay_disclosed": True,
        "match_score": 87,
        "summary": "Strong fit",
        "strong_matches": ["Kubernetes", "kubernetes"],
        "concerns": [],
        "missing_qualifications": [],
    }

    def fake_urlopen(request, timeout):
        assert request.full_url.endswith("/api/chat")
        body = json.loads(request.data)
        assert body["format"] == JOB_SCHEMA
        return _response(
            {
                "model": "qwen3:14b",
                "message": {"role": "assistant", "content": json.dumps(result)},
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OllamaAnalysisProvider("qwen3:14b")

    normalized, model = provider.analyze(_request())

    assert model == "qwen3:14b"
    assert normalized["company"] == "Example"
    assert normalized["pay_min"] == 150000.0
    assert normalized["pay_max"] == 200000.0
    assert normalized["strong_matches"] == ["Kubernetes"]


def test_job_analyzer_selects_builtin_ollama_provider(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        OllamaAnalysisProvider,
        "test_connection",
        lambda self: f"Connected to Ollama · {self.model}",
    )
    analyzer = JobAnalyzer(
        AppConfig(
            analysis_mode="generative",
            analysis_provider="ollama",
            openai_model="qwen3:14b",
        )
    )

    assert analyzer.test_connection() == "Connected to Ollama · qwen3:14b"
