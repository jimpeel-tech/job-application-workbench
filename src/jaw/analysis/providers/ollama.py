"""Ollama local structured-output analysis provider."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from ..contracts import AnalysisRequest
from ..normalization import normalize_result
from ..prompt import build_analysis_messages
from ..schema import JOB_SCHEMA

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:14b"


def _base_url(value: str | None = None) -> str:
    configured = (value or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_URL).strip()
    if "://" not in configured:
        configured = f"http://{configured}"
    return configured.rstrip("/")


def build_ollama_request_body(
    model: str,
    request: AnalysisRequest,
) -> dict[str, Any]:
    """Build a deterministic, non-streaming structured Ollama request."""
    return {
        "model": model,
        "messages": build_analysis_messages(request),
        "stream": False,
        "think": False,
        "format": JOB_SCHEMA,
        "keep_alive": "5m",
        "options": {
            "temperature": 0,
            "num_ctx": 8192,
            "num_predict": 2048,
        },
    }


class OllamaAnalysisProvider:
    """Local Ollama transport implementing ``AnalysisProvider``."""

    name = "ollama"

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        timeout: int = 180,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.base_url = _base_url(base_url)

    @property
    def tags_url(self) -> str:
        return f"{self.base_url}/api/tags"

    @property
    def chat_url(self) -> str:
        return f"{self.base_url}/api/chat"

    @property
    def available(self) -> bool:
        try:
            return self.model in self.list_models(timeout=2)
        except RuntimeError:
            return False

    def list_models(self, timeout: int = 5) -> list[str]:
        request = urllib.request.Request(self.tags_url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(self._http_error_message(error)) from error
        except (urllib.error.URLError, TimeoutError) as error:
            reason = getattr(error, "reason", error)
            raise RuntimeError(f"Could not reach Ollama: {reason}") from error
        except json.JSONDecodeError as error:
            raise RuntimeError("Ollama returned invalid response JSON") from error

        if not isinstance(payload, dict):
            raise RuntimeError("Ollama returned an invalid response object")
        models = payload.get("models") or []
        return [
            str(item.get("name") or item.get("model") or "").strip()
            for item in models
            if isinstance(item, dict) and (item.get("name") or item.get("model"))
        ]

    def test_connection(self) -> str:
        models = self.list_models(timeout=10)
        if self.model not in models:
            available = ", ".join(models) or "none"
            raise RuntimeError(
                f"Ollama model {self.model!r} is not installed (available: {available})"
            )
        return f"Connected to Ollama · {self.model}"

    def _execute_structured_body(
        self,
        body: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        http_request = urllib.request.Request(
            self.chat_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                http_request,
                timeout=self.timeout,
            ) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(self._http_error_message(error)) from error
        except (urllib.error.URLError, TimeoutError) as error:
            reason = getattr(error, "reason", error)
            raise RuntimeError(f"Could not reach Ollama: {reason}") from error
        except json.JSONDecodeError as error:
            raise RuntimeError("Ollama returned invalid response JSON") from error

        if not isinstance(payload, dict):
            raise RuntimeError("Ollama returned an invalid response object")
        if payload.get("error"):
            raise RuntimeError(f"Ollama response error: {payload['error']}")
        message = payload.get("message", {})
        content = str(message.get("content", "")) if isinstance(message, dict) else ""
        if not content:
            raise RuntimeError("Ollama response contained no output text")
        try:
            result = json.loads(content)
        except json.JSONDecodeError as error:
            raise RuntimeError("Ollama returned invalid structured JSON") from error
        if not isinstance(result, dict):
            raise RuntimeError("Ollama structured response must be a JSON object")
        model = str(payload.get("model") or self.model)
        return result, model

    def structured_chat(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        num_predict: int = 1200,
    ) -> tuple[dict[str, Any], str]:
        """Run a non-streaming structured chat without invoking job normalization."""
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "format": schema,
            "keep_alive": "5m",
            "options": {
                "temperature": 0,
                "num_ctx": 8192,
                "num_predict": int(num_predict),
            },
        }
        return self._execute_structured_body(body)

    def analyze(
        self,
        request: AnalysisRequest,
    ) -> tuple[dict[str, Any], str]:
        result, model = self._execute_structured_body(
            build_ollama_request_body(self.model, request)
        )
        return normalize_result(result), model

    @staticmethod
    def _http_error_message(error: urllib.error.HTTPError) -> str:
        detail = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(detail)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and payload.get("error"):
            return f"Ollama API error {error.code}: {payload['error']}"
        return f"Ollama API error {error.code}: {detail or error.reason}"
