import pytest

from jaw.application import JobAnalysisFailure, JobAnalysisService


class RecordingRepository:
    def __init__(self, *, failure_record_error: Exception | None = None) -> None:
        self.created: list[tuple[str, int]] = []
        self.updated: list[tuple[int, dict, str]] = []
        self.failures: list[tuple[int, str]] = []
        self.failure_record_error = failure_record_error

    def create_job(self, raw_description: str, user_id: int = 0) -> int:
        self.created.append((raw_description, user_id))
        return 42

    def update_analysis(self, job_id: int, result: dict, model: str) -> None:
        self.updated.append((job_id, result, model))

    def record_analysis_failure(self, job_id: int, message: str) -> None:
        if self.failure_record_error is not None:
            raise self.failure_record_error
        self.failures.append((job_id, message))


class StubAnalyzer:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure

    def analyze(self, description: str) -> tuple[dict, str]:
        if self.failure is not None:
            raise self.failure
        return {"summary": f"Analyzed {description}"}, "local"

    def test_connection(self) -> str:
        return "ready"


def test_job_analysis_service_preserves_create_analyze_update_order():
    repository = RecordingRepository()
    service = JobAnalysisService(repository, StubAnalyzer())

    outcome = service.analyze_new_job("Example posting", user_id=7)

    assert outcome.job_id == 42
    assert outcome.model == "local"
    assert repository.created == [("Example posting", 7)]
    assert repository.updated == [
        (42, {"summary": "Analyzed Example posting"}, "local")
    ]
    assert repository.failures == []


def test_job_remains_captured_and_failure_carries_job_id():
    repository = RecordingRepository()
    service = JobAnalysisService(
        repository,
        StubAnalyzer(failure=RuntimeError("provider unavailable")),
    )

    with pytest.raises(JobAnalysisFailure, match="provider unavailable") as captured:
        service.analyze_new_job("Example posting", user_id=7)

    assert captured.value.job_id == 42
    assert repository.created == [("Example posting", 7)]
    assert repository.updated == []
    assert repository.failures == [(42, "provider unavailable")]


def test_failure_recording_error_does_not_mask_analysis_error():
    repository = RecordingRepository(
        failure_record_error=RuntimeError("failure telemetry unavailable")
    )
    service = JobAnalysisService(
        repository,
        StubAnalyzer(failure=RuntimeError("provider unavailable")),
    )

    with pytest.raises(JobAnalysisFailure, match="provider unavailable") as captured:
        service.analyze_new_job("Example posting", user_id=7)

    assert captured.value.job_id == 42
