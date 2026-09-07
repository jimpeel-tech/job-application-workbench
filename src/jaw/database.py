from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .persistence import (
    CaptureRepository,
    DocumentWorkbenchRepository,
    JobRepository,
    OutlookRepository,
    QuestionRepository,
)
from .persistence.schema import SCHEMA, _ensure_column, initialize_schema


class JobDatabase:
    """Facade over JAW's focused SQLite repositories."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            initialize_schema(connection)

        # Resolve ``self.connect`` at call time so tests and embedding applications
        # can still replace the connection boundary after construction.
        connection_factory = lambda: self.connect()
        self.job_repository = JobRepository(connection_factory)
        self.capture_repository = CaptureRepository(connection_factory)
        self.question_repository = QuestionRepository(connection_factory)
        self.outlook_repository = OutlookRepository(connection_factory)
        self.document_workbench_repository = DocumentWorkbenchRepository(connection_factory)

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        name: str,
        declaration: str,
    ) -> None:
        _ensure_column(connection, table, name, declaration)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # JobRepository facade

    def create_job(self, description: str, user_id: int = 0) -> int:
        return self.job_repository.create_job(description, user_id)

    def update_analysis(
        self,
        job_id: int,
        result: dict[str, Any],
        model: str,
    ) -> None:
        self.job_repository.update_analysis(job_id, result, model)

    def set_status(
        self,
        job_id: int,
        status: str,
        user_id: int | None = None,
    ) -> None:
        self.job_repository.set_status(job_id, status, user_id)

    def update_identity(
        self,
        job_id: int,
        company: str,
        title: str,
        user_id: int | None = None,
    ) -> bool:
        return self.job_repository.update_identity(job_id, company, title, user_id)

    def delete_job(self, job_id: int, user_id: int | None = None) -> bool:
        return self.job_repository.delete_job(job_id, user_id)

    def get_job(
        self,
        job_id: int,
        user_id: int | None = None,
    ) -> dict[str, Any] | None:
        return self.job_repository.get_job(job_id, user_id)

    def list_jobs(
        self,
        search: str = "",
        sort: str = "created_at",
        order: str = "desc",
        status: str = "",
        remote: str = "",
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.job_repository.list_jobs(
            search=search,
            sort=sort,
            order=order,
            status=status,
            remote=remote,
            user_id=user_id,
        )

    # CaptureRepository facade

    def active_capture_session(self, user_id: int) -> dict[str, Any] | None:
        return self.capture_repository.active_capture_session(user_id)

    def start_capture_session(self, user_id: int) -> int:
        return self.capture_repository.start_capture_session(user_id)

    def get_or_create_capture_session(self, user_id: int) -> dict[str, Any]:
        return self.capture_repository.get_or_create_capture_session(user_id)

    def add_capture(
        self,
        user_id: int,
        content: str,
        *,
        content_type: str = "unclassified",
        classification_status: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.capture_repository.add_capture(
            user_id,
            content,
            content_type=content_type,
            classification_status=classification_status,
            metadata=metadata,
        )

    def set_capture_phase(
        self,
        user_id: int,
        phase: str,
        job_id: int | None = None,
    ) -> dict[str, Any]:
        return self.capture_repository.set_capture_phase(user_id, phase, job_id)

    def classify_capture_event(
        self,
        session_id: int,
        event_id: int,
        content_type: str,
        metadata: dict[str, Any],
    ) -> None:
        self.capture_repository.classify_capture_event(
            session_id,
            event_id,
            content_type,
            metadata,
        )

    def update_capture_metadata(
        self,
        session_id: int,
        event_id: int,
        metadata: dict[str, Any],
    ) -> None:
        self.capture_repository.update_capture_metadata(
            session_id,
            event_id,
            metadata,
        )

    # QuestionRepository facade

    def add_question(
        self,
        job_id: int,
        question: str,
        suggested_answer: str = "",
        submitted_answer: str = "",
    ) -> int:
        return self.question_repository.add_question(
            job_id,
            question,
            suggested_answer,
            submitted_answer,
        )

    def update_question(
        self,
        job_id: int,
        question_id: int,
        question: str,
        answer: str,
    ) -> bool:
        return self.question_repository.update_question(
            job_id,
            question_id,
            question,
            answer,
        )

    def delete_question(self, job_id: int, question_id: int) -> bool:
        return self.question_repository.delete_question(job_id, question_id)

    def submit_answer(self, question_id: int, answer: str) -> None:
        self.question_repository.submit_answer(question_id, answer)


__all__ = ["JobDatabase", "SCHEMA"]
