"""Persistence boundary for Outlook message processing and lifecycle decisions."""

from __future__ import annotations

import json
from typing import Any

from .types import ConnectionFactory


class OutlookRepository:
    def __init__(self, connect: ConnectionFactory) -> None:
        self._connect = connect

    def is_processed(self, user_id: int, message_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM outlook_messages WHERE user_id=? AND message_id=?",
                (user_id, message_id),
            ).fetchone()
            return row is not None

    def record_decision(
        self,
        *,
        user_id: int,
        message_id: str,
        internet_message_id: str = "",
        received_at: str = "",
        sender: str = "",
        subject: str = "",
        classification: str,
        category: str = "",
        job_id: int | None = None,
        classification_confidence: float = 0.0,
        match_confidence: float = 0.0,
        decision: str,
        event_type: str = "",
        event_details: str = "",
        new_status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Record one immutable message decision and optional job lifecycle update."""
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM outlook_messages WHERE user_id=? AND message_id=?",
                (user_id, message_id),
            ).fetchone()
            if exists:
                return False

            if job_id is not None:
                job = connection.execute(
                    "SELECT id,status FROM jobs WHERE id=? AND user_id=?",
                    (job_id, user_id),
                ).fetchone()
                if job is None:
                    job_id = None
                    new_status = None
                    event_type = ""
                elif new_status:
                    applied_time = received_at or None
                    connection.execute(
                        """
                        UPDATE jobs
                        SET status=?,
                            applied_at=CASE
                                WHEN ?='Applied' THEN COALESCE(applied_at,?,CURRENT_TIMESTAMP)
                                ELSE applied_at
                            END,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE id=? AND user_id=?
                        """,
                        (new_status, new_status, applied_time, job_id, user_id),
                    )

            if job_id is not None and event_type:
                connection.execute(
                    """
                    INSERT INTO application_events(
                        job_id,event_type,details,source,source_ref,metadata,occurred_at
                    ) VALUES (?,?,?,?,?,?,COALESCE(NULLIF(?,''),CURRENT_TIMESTAMP))
                    """,
                    (
                        job_id,
                        event_type,
                        event_details,
                        "outlook",
                        message_id,
                        metadata_json,
                        received_at,
                    ),
                )

            connection.execute(
                """
                INSERT INTO outlook_messages(
                    user_id,message_id,internet_message_id,received_at,sender,subject,
                    classification,category,job_id,classification_confidence,
                    match_confidence,decision,metadata
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    user_id,
                    message_id,
                    internet_message_id,
                    received_at,
                    sender,
                    subject,
                    classification,
                    category,
                    job_id,
                    float(classification_confidence),
                    float(match_confidence),
                    decision,
                    metadata_json,
                ),
            )
            return True

    def reset(self, user_id: int) -> dict[str, int]:
        """Undo JAW-side Outlook sync effects and make messages reprocessable.

        Statuses are restored only when the job still has the status written by Outlook,
        so a manual status change made after sync is never overwritten. Outlook-auth state
        is not touched. Existing Outlook categories are replaced naturally on the next sync.
        """
        with self._connect() as connection:
            rows = list(
                connection.execute(
                    """
                    SELECT id,message_id,job_id,metadata
                    FROM outlook_messages
                    WHERE user_id=?
                    ORDER BY id DESC
                    """,
                    (user_id,),
                )
            )
            restored = 0
            touched_jobs: set[int] = set()
            for row in rows:
                job_id = row["job_id"]
                if job_id is None:
                    continue
                try:
                    metadata = json.loads(row["metadata"] or "{}")
                except json.JSONDecodeError:
                    metadata = {}
                previous_status = str(metadata.get("previous_status", ""))
                new_status = str(metadata.get("new_status", ""))
                if not previous_status or not new_status:
                    continue
                current = connection.execute(
                    "SELECT status FROM jobs WHERE id=? AND user_id=?",
                    (int(job_id), user_id),
                ).fetchone()
                if current is None or str(current["status"]) != new_status:
                    continue
                connection.execute(
                    """
                    UPDATE jobs
                    SET status=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=? AND user_id=?
                    """,
                    (previous_status, int(job_id), user_id),
                )
                restored += 1
                touched_jobs.add(int(job_id))

            event_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM application_events
                WHERE source='outlook'
                  AND source_ref IN (
                    SELECT message_id FROM outlook_messages WHERE user_id=?
                  )
                """,
                (user_id,),
            ).fetchone()[0]
            connection.execute(
                """
                DELETE FROM application_events
                WHERE source='outlook'
                  AND source_ref IN (
                    SELECT message_id FROM outlook_messages WHERE user_id=?
                  )
                """,
                (user_id,),
            )

            for job_id in touched_jobs:
                applied_at = connection.execute(
                    """
                    SELECT MIN(occurred_at)
                    FROM application_events
                    WHERE job_id=? AND event_type='Applied'
                    """,
                    (job_id,),
                ).fetchone()[0]
                connection.execute(
                    "UPDATE jobs SET applied_at=? WHERE id=? AND user_id=?",
                    (applied_at, job_id, user_id),
                )

            connection.execute("DELETE FROM outlook_messages WHERE user_id=?", (user_id,))
            connection.execute("DELETE FROM outlook_sync_state WHERE user_id=?", (user_id,))
            return {
                "messages_reset": len(rows),
                "events_removed": int(event_count),
                "statuses_restored": restored,
            }

    def set_sync_state(
        self,
        user_id: int,
        *,
        scanned: int,
        updated: int,
        categorized: int,
        review: int,
        ignored: int,
        skipped: int,
        errors: int,
        truncated: bool,
        error: str = "",
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO outlook_sync_state(
                    user_id,last_sync_at,last_error,last_scanned,last_updated,
                    last_categorized,last_review,last_ignored,last_skipped,last_errors,last_truncated
                ) VALUES (?,CURRENT_TIMESTAMP,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                    last_sync_at=CURRENT_TIMESTAMP,
                    last_error=excluded.last_error,
                    last_scanned=excluded.last_scanned,
                    last_updated=excluded.last_updated,
                    last_categorized=excluded.last_categorized,
                    last_review=excluded.last_review,
                    last_ignored=excluded.last_ignored,
                    last_skipped=excluded.last_skipped,
                    last_errors=excluded.last_errors,
                    last_truncated=excluded.last_truncated
                """,
                (
                    user_id,
                    error,
                    scanned,
                    updated,
                    categorized,
                    review,
                    ignored,
                    skipped,
                    errors,
                    int(truncated),
                ),
            )

    def sync_state(self, user_id: int) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM outlook_sync_state WHERE user_id=?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else {}

    def recent_review(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT message_id,received_at,sender,subject,classification,category,
                       job_id,classification_confidence,match_confidence,decision,metadata
                FROM outlook_messages
                WHERE user_id=? AND decision='review'
                ORDER BY processed_at DESC,id DESC
                LIMIT ?
                """,
                (user_id, max(1, int(limit))),
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                try:
                    item["metadata"] = json.loads(item.get("metadata") or "{}")
                except json.JSONDecodeError:
                    item["metadata"] = {}
                result.append(item)
            return result


__all__ = ["OutlookRepository"]
