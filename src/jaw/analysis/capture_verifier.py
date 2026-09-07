from __future__ import annotations

from typing import Any

from ..smart_capture import (
    CAPTURE_VERIFICATION_SCHEMA,
    build_capture_verification_messages,
)
from .providers.ollama import OllamaAnalysisProvider


class OllamaCaptureVerifier:
    """Ephemeral Ollama verification for Smart Capture.

    This deliberately does not touch JobDatabase. It only returns structured facts
    that the desktop may merge into its temporary Smart Capture presentation.
    """

    def __init__(self, model: str, timeout: int = 90) -> None:
        self.provider = OllamaAnalysisProvider(model=model, timeout=timeout)

    def verify(
        self,
        description: str,
        parser_values: dict[str, tuple[str, ...]],
        mode: str,
    ) -> tuple[dict[str, Any], str]:
        messages = build_capture_verification_messages(
            description,
            parser_values,
            mode,
        )
        return self.provider.structured_chat(
            messages,
            CAPTURE_VERIFICATION_SCHEMA,
            num_predict=1200,
        )
