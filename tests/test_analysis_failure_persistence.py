from pathlib import Path

import pytest

from jaw.application import JobAnalysisFailure, JobAnalysisService
from jaw.database import JobDatabase


class FailingAnalyzer:
    def analyze(self, description: str) -> tuple[dict, str]:
        raise RuntimeError("provider unavailable")

    def test_connection(self) -> str:
        raise RuntimeError("provider unavailable")


def test_analysis_failure_preserves_capture_without_fake_analysis(tmp_path: Path):
    database = JobDatabase(tmp_path / "analysis-failure.db")
    service = JobAnalysisService(database, FailingAnalyzer())

    with pytest.raises(JobAnalysisFailure, match="provider unavailable") as captured:
        service.analyze_new_job("Example posting", user_id=7)

    job_id = captured.value.job_id
    job = database.get_job(job_id, user_id=7)
    assert job is not None
    assert job["raw_description"] == "Example posting"
    assert job["status"] == "Captured"
    assert job["summary"] == ""
    assert job["events"][0]["event_type"] == "AnalysisFailed"
    assert job["events"][0]["details"] == "provider unavailable"

    with database.connect() as connection:
        failure = connection.execute(
            """
            SELECT event_type,details,source
            FROM application_events
            WHERE job_id=? AND event_type='AnalysisFailed'
            """,
            (job_id,),
        ).fetchone()
        analysis_count = connection.execute(
            "SELECT COUNT(*) AS count FROM analysis_runs WHERE job_id=?",
            (job_id,),
        ).fetchone()["count"]

    assert dict(failure) == {
        "event_type": "AnalysisFailed",
        "details": "provider unavailable",
        "source": "analysis",
    }
    assert analysis_count == 0
