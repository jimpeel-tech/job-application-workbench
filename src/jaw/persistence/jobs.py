from __future__ import annotations

import json
from typing import Any

from .types import ConnectionFactory


class JobRepository:
    """Persistence operations for jobs, analysis runs, and lifecycle events."""

    def __init__(self, connect: ConnectionFactory) -> None:
        self._connect = connect

    def create_job(self, description: str, user_id: int = 0) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO jobs(user_id,raw_description) VALUES (?,?)",
                (user_id, description),
            )
            job_id = int(cursor.lastrowid)
            connection.execute(
                "INSERT INTO application_events(job_id,event_type) VALUES (?,?)",
                (job_id, "Captured"),
            )
            return job_id

    def update_analysis(
        self,
        job_id: int,
        result: dict[str, Any],
        model: str,
    ) -> None:
        list_fields = ("strong_matches", "concerns", "missing_qualifications")
        values = dict(result)
        for field in list_fields:
            values[field] = json.dumps(values.get(field, []), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs SET
                  company=?, title=?, location=?, remote_status=?,
                  pay_min=?, pay_max=?, currency=?, pay_period=?,
                  pay_disclosed=?, match_score=?, summary=?,
                  strong_matches=?, concerns=?, missing_qualifications=?,
                  status=CASE
                    WHEN status IN ('Captured','Analyzed','Reviewing') THEN 'Reviewing'
                    ELSE status
                  END,
                  updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    values.get("company", ""),
                    values.get("title", ""),
                    values.get("location", ""),
                    values.get("remote_status", "Unclear"),
                    values.get("pay_min"),
                    values.get("pay_max"),
                    values.get("currency", ""),
                    values.get("pay_period", ""),
                    int(bool(values.get("pay_disclosed", False))),
                    values.get("match_score"),
                    values.get("summary", ""),
                    values.get("strong_matches", "[]"),
                    values.get("concerns", "[]"),
                    values.get("missing_qualifications", "[]"),
                    job_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO analysis_runs(job_id,model,prompt_version,raw_result)
                VALUES (?,?,?,?)
                """,
                (job_id, model, "brief-v1", json.dumps(result, ensure_ascii=False)),
            )
            connection.execute(
                """
                INSERT INTO application_events(job_id,event_type,details)
                VALUES (?,?,?)
                """,
                (job_id, "Analyzed", f"Model: {model}"),
            )

    def set_status(
        self,
        job_id: int,
        status: str,
        user_id: int | None = None,
    ) -> None:
        with self._connect() as connection:
            owner_clause = " AND user_id=?" if user_id is not None else ""
            parameters: list[Any] = [status, status, job_id]
            if user_id is not None:
                parameters.append(user_id)
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status=?,
                    applied_at=CASE
                        WHEN ?='Applied' THEN COALESCE(applied_at,CURRENT_TIMESTAMP)
                        ELSE applied_at
                    END,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """
                + owner_clause,
                parameters,
            )
            if not cursor.rowcount:
                return
            connection.execute(
                "INSERT INTO application_events(job_id,event_type) VALUES (?,?)",
                (job_id, status),
            )

    def update_identity(
        self,
        job_id: int,
        company: str,
        title: str,
        user_id: int | None = None,
    ) -> bool:
        company = company.strip()
        title = title.strip()
        if not company or not title:
            raise ValueError("Company and role / title are required")
        with self._connect() as connection:
            sql = (
                "UPDATE jobs SET company=?, title=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE id=?"
            )
            parameters: list[Any] = [company, title, job_id]
            if user_id is not None:
                sql += " AND user_id=?"
                parameters.append(user_id)
            cursor = connection.execute(sql, parameters)
            return cursor.rowcount > 0

    def delete_job(self, job_id: int, user_id: int | None = None) -> bool:
        with self._connect() as connection:
            sql = "DELETE FROM jobs WHERE id=?"
            parameters: list[Any] = [job_id]
            if user_id is not None:
                sql += " AND user_id=?"
                parameters.append(user_id)
            cursor = connection.execute(sql, parameters)
            return cursor.rowcount > 0

    def get_job(
        self,
        job_id: int,
        user_id: int | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            sql = "SELECT * FROM jobs WHERE id=?"
            parameters: list[Any] = [job_id]
            if user_id is not None:
                sql += " AND user_id=?"
                parameters.append(user_id)
            row = connection.execute(sql, parameters).fetchone()
            if row is None:
                return None
            result = dict(row)
            for field in ("strong_matches", "concerns", "missing_qualifications"):
                result[field] = json.loads(result[field] or "[]")
            result["questions"] = [
                dict(question)
                for question in connection.execute(
                    "SELECT * FROM questions WHERE job_id=? ORDER BY id",
                    (job_id,),
                )
            ]
            result["events"] = [
                dict(event)
                for event in connection.execute(
                    """
                    SELECT event_type,details,occurred_at
                    FROM application_events
                    WHERE job_id=? ORDER BY id DESC
                    """,
                    (job_id,),
                )
            ]
            return result

    def list_jobs(
        self,
        search: str = "",
        sort: str = "created_at",
        order: str = "desc",
        status: str = "",
        remote: str = "",
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        allowed_sorts = {
            "created_at",
            "updated_at",
            "company",
            "title",
            "match_score",
            "pay_min",
            "pay_max",
            "status",
            "remote_status",
        }
        sort = sort if sort in allowed_sorts else "created_at"
        direction = "ASC" if order.lower() == "asc" else "DESC"
        clauses: list[str] = []
        parameters: list[Any] = []
        if user_id is not None:
            clauses.append("user_id=?")
            parameters.append(user_id)
        if search:
            clauses.append(
                "(company LIKE ? OR title LIKE ? OR raw_description LIKE ? OR summary LIKE ?)"
            )
            term = f"%{search}%"
            parameters.extend([term, term, term, term])
        if status:
            clauses.append("status=?")
            parameters.append(status)
        if remote:
            clauses.append("remote_status=?")
            parameters.append(remote)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id,company,title,location,remote_status,pay_min,pay_max,
                       currency,pay_period,match_score,status,applied_at,
                       created_at,updated_at,
                       (SELECT COUNT(*) FROM questions q WHERE q.job_id=jobs.id)
                           AS question_count
                FROM jobs {where}
                ORDER BY {sort} {direction}, id DESC
                """,
                parameters,
            )
            return [dict(row) for row in rows]
