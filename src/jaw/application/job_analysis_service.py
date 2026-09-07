from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class JobAnalysisRepository(Protocol):
    def create_job(self, raw_description: str, user_id: int = 0) -> int: ...

    def update_analysis(
        self,
        job_id: int,
        result: dict[str, Any],
        model: str,
    ) -> None: ...


class AnalysisEngine(Protocol):
    def analyze(self, description: str) -> tuple[dict[str, Any], str]: ...

    def test_connection(self) -> str: ...


@dataclass(frozen=True)
class AnalysisOutcome:
    job_id: int
    model: str


class JobAnalysisService:
    """Create, analyze, and persist one captured job description."""

    def __init__(
        self,
        repository: JobAnalysisRepository,
        analyzer: AnalysisEngine,
    ) -> None:
        self.repository = repository
        self.analyzer = analyzer

    def analyze_new_job(
        self,
        description: str,
        user_id: int,
    ) -> AnalysisOutcome:
        job_id = self.repository.create_job(description, user_id)
        result, model = self.analyzer.analyze(description)
        self.repository.update_analysis(job_id, result, model)
        return AnalysisOutcome(job_id=job_id, model=model)
