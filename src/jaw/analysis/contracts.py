"""Contracts shared by analysis services and provider implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AnalysisRequest:
    """Provider-neutral input assembled for one job analysis."""

    description: str
    candidate: dict[str, Any]
    extracted_job: dict[str, Any]


class AnalysisProvider(Protocol):
    """Provider contract for generative or deterministic analysis backends."""

    name: str

    @property
    def available(self) -> bool:
        ...

    def test_connection(self) -> str:
        ...

    def analyze(
        self,
        request: AnalysisRequest,
    ) -> tuple[dict[str, Any], str]:
        ...
