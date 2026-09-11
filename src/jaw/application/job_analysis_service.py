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

    def record_analysis_failure(self, job_id: int, message: str) -> None: ...


class AnalysisEngine(Protocol):
    def analyze(self, description: str) -> tuple[dict[str, Any], str]: ...

    def test_connection(self) -> str: ...


@dataclass(frozen=True)
class AnalysisOutcome:
    job_id: int
    model: str


class JobAnalysisFailure(RuntimeError):
    """Analysis failed after the raw job was successfully captured."""

    def __init__(self, job_id: int, message: str) -> None:
        super().__init__(message)
        self.job_id = int(job_id)


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
        try:
            result, model = self.analyzer.analyze(description)
            self.repository.update_analysis(job_id, result, model)
        except Exception as error:
            self._record_failure(job_id, error)
            raise JobAnalysisFailure(job_id, str(error)) from error
        return AnalysisOutcome(job_id=job_id, model=model)

    def _record_failure(self, job_id: int, error: Exception) -> None:
        recorder = getattr(self.repository, "record_analysis_failure", None)
        if not callable(recorder):
            return
        message = " ".join(str(error).split()).strip() or type(error).__name__
        try:
            recorder(job_id, message[:1000])
        except Exception:
            # Failure telemetry must never replace the original provider or
            # persistence error that the caller needs to surface.
            pass


__all__ = [
    "AnalysisEngine",
    "AnalysisOutcome",
    "JobAnalysisFailure",
    "JobAnalysisRepository",
    "JobAnalysisService",
]
