"""OpenAI Responses API analysis provider."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..contracts import AnalysisRequest
from ..normalization import normalize_result
from ..prompt import build_analysis_messages
from ..schema import JOB_SCHEMA


def build_openai_request_body(
    model: str,
    request: AnalysisRequest,
) -> dict[str, Any]:
    """Build the provider request separately from HTTP transport."""
    return {
        "model": model,
        "input": build_analysis_messages(request),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "job_analysis",
                "strict": True,
                "schema": JOB_SCHEMA,
            }
        },
        "store": False,
    }


class OpenAIAnalysisProvider:
    """OpenAI Responses API transport implementing ``AnalysisProvider``."""

    name = "openai"
    responses_url = "https://api.openai.com/v1/responses"
    models_url = "https://api.openai.com/v1/models"

    def __init__(
        self,
        model: str,
        timeout: int = 90,
    ) -> None:
        self.model = model
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    @property
    def api_key(self) -> str:
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not available to JAW")
        return key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def test_connection(self) -> str:
        model_path = urllib.parse.quote(self.model, safe="")
        request = urllib.request.Request(
            f"{self.models_url}/{model_path}",
            headers={
                "Authorization": f"Bearer {self.api_key}",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(self._http_error_message(error)) from error
        except (urllib.error.URLError, TimeoutError) as error:
            reason = getattr(error, "reason", error)
            raise RuntimeError(f"Could not reach OpenAI: {reason}") from error
        except json.JSONDecodeError as error:
            raise RuntimeError("OpenAI returned invalid response JSON") from error

        if not isinstance(payload, dict):
            raise RuntimeError("OpenAI returned an invalid response object")
        return f"Connected to OpenAI · {payload.get('id', self.model)}"

    def analyze(
        self,
        request: AnalysisRequest,
    ) -> tuple[dict[str, Any], str]:
        request_body = build_openai_request_body(self.model, request)

        http_request = urllib.request.Request(
            self.responses_url,
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
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
            raise RuntimeError(f"Could not reach OpenAI: {reason}") from error
        except json.JSONDecodeError as error:
            raise RuntimeError("OpenAI returned invalid response JSON") from error

        if not isinstance(payload, dict):
            raise RuntimeError("OpenAI returned an invalid response object")
        text = self._response_text(payload)
        try:
            result = json.loads(text)
        except json.JSONDecodeError as error:
            raise RuntimeError("OpenAI returned invalid structured JSON") from error
        if not isinstance(result, dict):
            raise RuntimeError("OpenAI structured response must be a JSON object")

        model = str(payload.get("model") or self.model)
        return normalize_result(result), model

    @staticmethod
    def _response_text(payload: dict[str, Any]) -> str:
        if payload.get("output_text"):
            return str(payload["output_text"])

        for output in payload.get("output", []):
            if not isinstance(output, dict) or output.get("type") != "message":
                continue

            for content in output.get("content", []):
                if not isinstance(content, dict):
                    continue
                content_type = content.get("type")
                if content_type == "output_text":
                    return str(content.get("text", ""))
                if content_type == "refusal":
                    refusal = str(content.get("refusal", "")).strip()
                    raise RuntimeError(
                        refusal or "OpenAI declined to produce an analysis"
                    )

        error = payload.get("error")
        if error:
            if isinstance(error, dict):
                message = error.get("message") or error.get("code")
                if message:
                    raise RuntimeError(f"OpenAI response error: {message}")
            raise RuntimeError(f"OpenAI response error: {error}")

        raise RuntimeError("OpenAI response contained no output text")

    @staticmethod
    def _http_error_message(
        error: urllib.error.HTTPError,
    ) -> str:
        detail = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(detail)
        except json.JSONDecodeError:
            payload = None

        if isinstance(payload, dict):
            api_error = payload.get("error")
            if isinstance(api_error, dict):
                message = api_error.get("message")
                if message:
                    return f"OpenAI API error {error.code}: {message}"

        return f"OpenAI API error {error.code}: {detail or error.reason}"
