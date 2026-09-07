from __future__ import annotations

import json
from typing import Any

from .types import ConnectionFactory


class CaptureRepository:
    """Persistence operations for capture sessions and their event journal."""

    def __init__(self, connect: ConnectionFactory) -> None:
        self._connect = connect

    def active_capture_session(self, user_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM capture_sessions
                WHERE user_id=? AND status='active'
                ORDER BY id DESC LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["events"] = [
                dict(event)
                for event in connection.execute(
                    """
                    SELECT id,content,content_type,classification_status,
                           job_id,metadata,created_at
                    FROM capture_events
                    WHERE session_id=? ORDER BY id
                    """,
                    (int(row["id"]),),
                )
            ]
            return result

    def start_capture_session(self, user_id: int) -> int:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE capture_sessions
                SET status='cleared',ended_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                WHERE user_id=? AND status='active'
                """,
                (user_id,),
            )
            cursor = connection.execute(
                "INSERT INTO capture_sessions(user_id) VALUES (?)",
                (user_id,),
            )
            return int(cursor.lastrowid)

    def get_or_create_capture_session(self, user_id: int) -> dict[str, Any]:
        session = self.active_capture_session(user_id)
        if session is not None:
            return session
        self.start_capture_session(user_id)
        session = self.active_capture_session(user_id)
        if session is None:
            raise RuntimeError("Capture session could not be created")
        return session

    def add_capture(
        self,
        user_id: int,
        content: str,
        *,
        content_type: str = "unclassified",
        classification_status: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.get_or_create_capture_session(user_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO capture_events(
                    session_id,content,content_type,classification_status,
                    job_id,metadata
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    int(session["id"]),
                    content,
                    content_type,
                    classification_status,
                    session.get("job_id"),
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            connection.execute(
                "UPDATE capture_sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (int(session["id"]),),
            )
        refreshed = self.active_capture_session(user_id)
        if refreshed is None:
            raise RuntimeError("Capture session could not be read")
        return refreshed

    def set_capture_phase(
        self,
        user_id: int,
        phase: str,
        job_id: int | None = None,
    ) -> dict[str, Any]:
        if phase not in {"job_capture", "application"}:
            raise ValueError(f"Unsupported capture phase: {phase}")
        session = self.get_or_create_capture_session(user_id)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE capture_sessions
                SET phase=?,job_id=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (phase, job_id, int(session["id"])),
            )
        refreshed = self.active_capture_session(user_id)
        if refreshed is None:
            raise RuntimeError("Capture session could not be read")
        return refreshed

    def classify_capture_event(
        self,
        session_id: int,
        event_id: int,
        content_type: str,
        metadata: dict[str, Any],
    ) -> None:
        status = "pending" if content_type == "unclassified" else "classified"
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE capture_events
                SET content_type=?,classification_status=?,metadata=?
                WHERE id=? AND session_id=?
                """,
                (
                    content_type,
                    status,
                    json.dumps(metadata, ensure_ascii=False),
                    event_id,
                    session_id,
                ),
            )

    def update_capture_metadata(
        self,
        session_id: int,
        event_id: int,
        metadata: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE capture_events SET metadata=? WHERE id=? AND session_id=?",
                (json.dumps(metadata, ensure_ascii=False), event_id, session_id),
            )
