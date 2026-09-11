from __future__ import annotations

import io

import pytest

from jaw.analysis.contracts import AnalysisRequest
from jaw.analysis.providers.ollama import OllamaAnalysisProvider
from jaw.analysis.providers.openai import OpenAIAnalysisProvider


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _request() -> AnalysisRequest:
    return AnalysisRequest(
        description="Example role",
        candidate={"capabilities": []},
        extracted_job={"fields": {}},
    )


def test_openai_timeout_is_exposed_as_provider_error(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def timeout(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", timeout)
    provider = OpenAIAnalysisProvider("gpt-test")

    with pytest.raises(RuntimeError, match="Could not reach OpenAI: timed out"):
        provider.analyze(_request())


def test_openai_invalid_http_json_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"not-json"),
    )
    provider = OpenAIAnalysisProvider("gpt-test")

    with pytest.raises(RuntimeError, match="OpenAI returned invalid response JSON"):
        provider.analyze(_request())


def test_openai_non_object_response_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"[]"),
    )
    provider = OpenAIAnalysisProvider("gpt-test")

    with pytest.raises(RuntimeError, match="OpenAI returned an invalid response object"):
        provider.analyze(_request())


def test_ollama_invalid_http_json_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"not-json"),
    )
    provider = OllamaAnalysisProvider("qwen3:14b")

    with pytest.raises(RuntimeError, match="Ollama returned invalid response JSON"):
        provider.analyze(_request())


def test_ollama_non_object_response_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"[]"),
    )
    provider = OllamaAnalysisProvider("qwen3:14b")

    with pytest.raises(RuntimeError, match="Ollama returned an invalid response object"):
        provider.analyze(_request())
