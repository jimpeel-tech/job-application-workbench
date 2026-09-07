"""Provider-neutral text generation for document expression and Function outputs."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..config import RATING_GUIDANCE

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:14b"


@dataclass(frozen=True)
class TextGenerationRequest:
    """One named expression plus its explicitly selected evidence context."""

    expression_key: str
    instructions: str
    context: dict[str, Any]
    provider: str
    model: str
    max_length: int | None = None
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TextGenerationResult:
    """Generated replacement text and provider provenance."""

    text: str
    provider: str
    model: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StructuredTextGenerationRequest:
    """A schema-constrained Function generation block.

    Workbench generation blocks intentionally support only ``text`` and
    ``list`` outputs. Structured evidence remains separate from the rendered
    instruction text so providers receive real JSON data instead of a prose dump.
    """

    variable_name: str
    instructions: str
    context: dict[str, Any]
    provider: str
    model: str
    output_type: str = "text"
    max_length: int | None = None
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StructuredTextGenerationResult:
    """Validated native value returned by a Function generation block."""

    value: str | list[str]
    provider: str
    model: str
    evidence: dict[str, Any] = field(default_factory=dict)


class TextGenerator(Protocol):
    """Injectable transport for document text generation."""

    def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        ...

    def generate_structured(
        self,
        request: StructuredTextGenerationRequest,
    ) -> StructuredTextGenerationResult:
        ...


class ProviderTextGenerator:
    """Bounded Ollama/OpenAI runtime selected from inherited user settings."""

    def __init__(self, *, timeout: int = 180) -> None:
        self.timeout = timeout

    def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        provider = request.provider.strip().casefold()
        if provider == "ollama":
            return self._ollama(request)
        if provider == "openai":
            return self._openai(request)
        raise RuntimeError(f"Unsupported document generation provider: {provider}")

    def generate_structured(
        self,
        request: StructuredTextGenerationRequest,
    ) -> StructuredTextGenerationResult:
        provider = request.provider.strip().casefold()
        output_type = _output_type(request.output_type)
        if provider == "ollama":
            return self._ollama_structured(request, output_type)
        if provider == "openai":
            return self._openai_structured(request, output_type)
        raise RuntimeError(f"Unsupported document generation provider: {provider}")

    def _ollama(self, request: TextGenerationRequest) -> TextGenerationResult:
        base_url = (os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_URL).strip()
        if "://" not in base_url:
            base_url = f"http://{base_url}"
        body = {
            "model": request.model or DEFAULT_OLLAMA_MODEL,
            "messages": _messages(request),
            "stream": False,
            "think": False,
            "keep_alive": "5m",
            "options": {
                "temperature": _temperature(request.settings),
                "num_ctx": 8192,
                "num_predict": _token_limit(request.max_length),
            },
        }
        payload = _json_request(
            f"{base_url.rstrip('/')}/api/chat",
            body,
            timeout=self.timeout,
        )
        if payload.get("error"):
            raise RuntimeError(f"Ollama response error: {payload['error']}")
        message = payload.get("message", {})
        text = str(message.get("content", "")).strip()
        if not text:
            raise RuntimeError("Ollama response contained no output text")
        return TextGenerationResult(
            text=text,
            provider="ollama",
            model=str(payload.get("model") or request.model),
        )

    def _openai(self, request: TextGenerationRequest) -> TextGenerationResult:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not available to JAW")
        body = {
            "model": request.model,
            "input": _messages(request),
            "store": False,
            "max_output_tokens": _token_limit(request.max_length),
        }
        payload = _json_request(
            "https://api.openai.com/v1/responses",
            body,
            timeout=min(self.timeout, 120),
            headers={"Authorization": f"Bearer {api_key}"},
        )
        text = _openai_response_text(payload)
        return TextGenerationResult(
            text=text.strip(),
            provider="openai",
            model=str(payload.get("model") or request.model),
        )

    def _ollama_structured(
        self,
        request: StructuredTextGenerationRequest,
        output_type: str,
    ) -> StructuredTextGenerationResult:
        base_url = (os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_URL).strip()
        if "://" not in base_url:
            base_url = f"http://{base_url}"
        schema = _structured_schema(output_type)
        body = {
            "model": request.model or DEFAULT_OLLAMA_MODEL,
            "messages": _structured_messages(request, output_type),
            "stream": False,
            "think": False,
            "format": schema,
            "keep_alive": "5m",
            "options": {
                "temperature": _temperature(request.settings),
                "num_ctx": 8192,
                "num_predict": _token_limit(request.max_length),
            },
        }
        payload = _json_request(
            f"{base_url.rstrip('/')}/api/chat",
            body,
            timeout=self.timeout,
        )
        if payload.get("error"):
            raise RuntimeError(f"Ollama response error: {payload['error']}")
        message = payload.get("message", {})
        content = str(message.get("content", "")).strip()
        if not content:
            raise RuntimeError("Ollama response contained no structured output")
        value = _structured_value(content, output_type)
        return StructuredTextGenerationResult(
            value=value,
            provider="ollama",
            model=str(payload.get("model") or request.model),
            evidence={"output_type": output_type},
        )

    def _openai_structured(
        self,
        request: StructuredTextGenerationRequest,
        output_type: str,
    ) -> StructuredTextGenerationResult:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not available to JAW")
        schema = _structured_schema(output_type)
        body = {
            "model": request.model,
            "input": _structured_messages(request, output_type),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "jaw_function_output",
                    "strict": True,
                    "schema": schema,
                }
            },
            "store": False,
            "max_output_tokens": _token_limit(request.max_length),
        }
        payload = _json_request(
            "https://api.openai.com/v1/responses",
            body,
            timeout=min(self.timeout, 120),
            headers={"Authorization": f"Bearer {api_key}"},
        )
        value = _structured_value(_openai_response_text(payload), output_type)
        return StructuredTextGenerationResult(
            value=value,
            provider="openai",
            model=str(payload.get("model") or request.model),
            evidence={"output_type": output_type},
        )


def _messages(request: TextGenerationRequest) -> list[dict[str, str]]:
    rating_scale = _rating_scale()
    system = (
        "Write only the replacement text requested by the document expression. "
        "Use only the supplied context. Do not invent candidate experience, "
        "qualifications, capability ratings, measurements, or job facts. "
        "A missing capability rating means no rating was provided. "
        f"The authoritative JAW capability scale is: {rating_scale}."
    )
    context_json = json.dumps(request.context, ensure_ascii=False, indent=2)
    maximum = (
        f"\nHard maximum: {request.max_length} characters."
        if request.max_length is not None
        else ""
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"Expression: {request.expression_key}\n"
                f"Instructions:\n{request.instructions}{maximum}\n\n"
                f"Context (the only permitted evidence):\n{context_json}"
            ),
        },
    ]


def _structured_messages(
    request: StructuredTextGenerationRequest,
    output_type: str,
) -> list[dict[str, str]]:
    rating_scale = _rating_scale()
    system = (
        "Produce only the requested structured Function value. Use only the supplied "
        "JSON context as evidence. Do not invent candidate experience, qualifications, "
        "capability ratings, measurements, or job facts. The response must match the "
        "provided JSON schema exactly. A missing capability rating means no rating was "
        f"provided. The authoritative JAW capability scale is: {rating_scale}."
    )
    context_json = json.dumps(request.context, ensure_ascii=False, indent=2)
    maximum = (
        f"\nHard maximum per returned string: {request.max_length} characters."
        if request.max_length is not None
        else ""
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"Function variable: {request.variable_name}\n"
                f"Return type: {output_type}\n"
                f"Instructions:\n{request.instructions.strip()}{maximum}\n\n"
                "Structured context (the only permitted evidence):\n"
                f"{context_json}"
            ),
        },
    ]


def _rating_scale() -> str:
    return "; ".join(
        f"{rating}={guidance['label']} ({guidance['description']})"
        for rating, guidance in RATING_GUIDANCE.items()
    )


def _structured_schema(output_type: str) -> dict[str, Any]:
    if output_type == "list":
        value_schema: dict[str, Any] = {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
        }
    else:
        value_schema = {"type": "string", "minLength": 1}
    return {
        "type": "object",
        "properties": {"value": value_schema},
        "required": ["value"],
        "additionalProperties": False,
    }


def _structured_value(raw: str, output_type: str) -> str | list[str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("Generation provider returned invalid structured JSON") from error
    if not isinstance(payload, dict) or set(payload) != {"value"}:
        raise RuntimeError("Generation provider returned an invalid structured object")
    value = payload["value"]
    if output_type == "text":
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError("Generation provider returned an invalid text value")
        return value.strip()
    if not isinstance(value, list) or not value:
        raise RuntimeError("Generation provider returned an invalid list value")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise RuntimeError("Generation provider list values must be non-empty strings")
    return [item.strip() for item in value]


def _output_type(value: str) -> str:
    normalized = str(value or "text").strip().casefold()
    if normalized not in {"text", "list"}:
        raise RuntimeError("Structured generation output must be text or list")
    return normalized


def _temperature(settings: dict[str, Any]) -> float:
    try:
        value = float(settings.get("temperature", 0))
    except (TypeError, ValueError):
        value = 0
    return min(2.0, max(0.0, value))


def _token_limit(max_length: int | None) -> int:
    if max_length is None:
        return 1024
    return min(4096, max(32, (int(max_length) + 1) // 2))


def _json_request(
    url: str,
    body: dict[str, Any],
    *,
    timeout: int,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Text generation API error {error.code}: {detail}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        reason = getattr(error, "reason", error)
        raise RuntimeError(f"Could not reach text generation provider: {reason}") from error
    if not isinstance(payload, dict):
        raise RuntimeError("Text generation provider returned an invalid response")
    return payload


def _openai_response_text(payload: dict[str, Any]) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    for output in payload.get("output", []):
        if not isinstance(output, dict) or output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                return str(content.get("text", ""))
    error = payload.get("error")
    if error:
        raise RuntimeError(f"OpenAI response error: {error}")
    raise RuntimeError("OpenAI response contained no output text")


__all__ = [
    "DEFAULT_OLLAMA_MODEL",
    "ProviderTextGenerator",
    "StructuredTextGenerationRequest",
    "StructuredTextGenerationResult",
    "TextGenerationRequest",
    "TextGenerationResult",
    "TextGenerator",
]
