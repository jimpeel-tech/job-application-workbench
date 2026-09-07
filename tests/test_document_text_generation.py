from __future__ import annotations

import json

from jaw.documents import text_generation
from jaw.documents.text_generation import (
    ProviderTextGenerator,
    StructuredTextGenerationRequest,
)


def test_ollama_structured_generation_uses_json_schema(monkeypatch) -> None:
    captured = {}

    def fake_request(url, body, *, timeout, headers=None):
        captured.update({"url": url, "body": body, "timeout": timeout, "headers": headers})
        return {
            "model": "qwen3:14b",
            "message": {"content": json.dumps({"value": ["One", "Two"]})},
        }

    monkeypatch.setattr(text_generation, "_json_request", fake_request)
    generator = ProviderTextGenerator(timeout=9)
    result = generator.generate_structured(
        StructuredTextGenerationRequest(
            variable_name="bullets",
            instructions="Generate two bullets from jobs.",
            context={"jobs": [{"company": "Example"}]},
            provider="ollama",
            model="qwen3:14b",
            output_type="list",
        )
    )

    assert result.value == ["One", "Two"]
    schema = captured["body"]["format"]
    assert schema["properties"]["value"]["type"] == "array"
    assert schema["additionalProperties"] is False
    assert '"jobs"' in captured["body"]["messages"][1]["content"]


def test_openai_structured_generation_uses_strict_text_schema(monkeypatch) -> None:
    captured = {}

    def fake_request(url, body, *, timeout, headers=None):
        captured.update({"url": url, "body": body, "timeout": timeout, "headers": headers})
        return {
            "model": "example-model",
            "output_text": json.dumps({"value": "Concise paragraph"}),
        }

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(text_generation, "_json_request", fake_request)
    generator = ProviderTextGenerator(timeout=9)
    result = generator.generate_structured(
        StructuredTextGenerationRequest(
            variable_name="summary",
            instructions="Write one paragraph.",
            context={"job": {"title": "Staff SRE"}},
            provider="openai",
            model="example-model",
            output_type="text",
        )
    )

    assert result.value == "Concise paragraph"
    fmt = captured["body"]["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["strict"] is True
    assert fmt["schema"]["properties"]["value"]["type"] == "string"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
