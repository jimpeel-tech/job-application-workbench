from jaw.application import JobAnalysisFailure
from jaw.desktop.workers import BriefWorker


class FailingService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def analyze_new_job(self, description: str, user_id: int):
        raise self.error


def test_brief_worker_emits_captured_job_id_for_analysis_failure():
    worker = BriefWorker(
        FailingService(JobAnalysisFailure(42, "provider unavailable")),
        "Example posting",
        7,
    )
    failures: list[tuple[int, str]] = []
    worker.failed.connect(lambda job_id, message: failures.append((job_id, message)))

    worker.run()

    assert failures == [(42, "provider unavailable")]


def test_brief_worker_uses_zero_only_when_no_job_identity_exists():
    worker = BriefWorker(
        FailingService(RuntimeError("capture failed")),
        "Example posting",
        7,
    )
    failures: list[tuple[int, str]] = []
    worker.failed.connect(lambda job_id, message: failures.append((job_id, message)))

    worker.run()

    assert failures == [(0, "capture failed")]
