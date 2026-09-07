from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..analysis.capture_verifier import OllamaCaptureVerifier
from ..application.job_analysis_service import AnalysisEngine, JobAnalysisService


class BriefWorker(QThread):
    completed = Signal(int, str)
    failed = Signal(int, str)

    def __init__(
        self,
        service: JobAnalysisService,
        description: str,
        user_id: int,
    ) -> None:
        super().__init__()
        self.service = service
        self.description = description
        self.user_id = user_id

    def run(self) -> None:
        job_id = 0
        try:
            outcome = self.service.analyze_new_job(
                self.description,
                self.user_id,
            )
            job_id = outcome.job_id
            self.completed.emit(outcome.job_id, outcome.model)
        except Exception as error:
            self.failed.emit(job_id, str(error))


class CaptureVerificationWorker(QThread):
    completed = Signal(int, dict, str)
    failed = Signal(int, str)

    def __init__(
        self,
        description: str,
        parser_values: dict[str, tuple[str, ...]],
        mode: str,
        model: str,
        generation: int,
    ) -> None:
        super().__init__()
        self.description = description
        self.parser_values = parser_values
        self.mode = mode
        self.model = model
        self.generation = generation

    def run(self) -> None:
        try:
            payload, model = OllamaCaptureVerifier(self.model).verify(
                self.description,
                self.parser_values,
                self.mode,
            )
            self.completed.emit(self.generation, payload, model)
        except Exception as error:
            self.failed.emit(self.generation, str(error))


class ConnectionTestWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, analyzer: AnalysisEngine) -> None:
        super().__init__()
        self.analyzer = analyzer

    def run(self) -> None:
        try:
            self.completed.emit(self.analyzer.test_connection())
        except Exception as error:
            self.failed.emit(str(error))
