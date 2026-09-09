from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DEMO_USER_NAME = "Ol Sarge"
DEMO_JOBS_FORMAT = "jaw-demo-jobs"
DEMO_JOBS_SEED_KEY_PREFIX = "demo_jobs_seed_version"
DEFAULT_DEMO_JOBS_PATH = Path(__file__).with_name("resources") / "default-jobs-v1.0.json"

JOB_FIELDS = (
    "company",
    "title",
    "location",
    "remote_status",
    "source_url",
    "raw_description",
    "pay_min",
    "pay_max",
    "currency",
    "pay_period",
    "pay_disclosed",
    "match_score",
    "summary",
    "strong_matches",
    "concerns",
    "missing_qualifications",
    "status",
)
JSON_LIST_FIELDS = ("strong_matches", "concerns", "missing_qualifications")


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _active_demo_user_id(connection: sqlite3.Connection) -> int | None:
    if not _table_exists(connection, "user_accounts") or not _table_exists(
        connection, "user_preferences"
    ):
        return None

    preference = connection.execute(
        "SELECT value FROM user_preferences WHERE key='active_user_id'"
    ).fetchone()
    if preference is None:
        return None

    try:
        user_id = int(preference[0])
    except (TypeError, ValueError):
        return None

    row = connection.execute(
        "SELECT name FROM user_accounts WHERE id=?",
        (user_id,),
    ).fetchone()
    if row is None or str(row[0]).casefold() != DEMO_USER_NAME.casefold():
        return None
    return user_id


def _load_fixture(path: Path) -> tuple[int, list[dict[str, Any]]] | None:
    if not path.is_file():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Demo jobs fixture must contain a JSON object")
    if payload.get("format") != DEMO_JOBS_FORMAT:
        raise ValueError(f"Unsupported demo jobs fixture format: {payload.get('format')!r}")

    try:
        version = int(payload.get("version", 0))
    except (TypeError, ValueError) as error:
        raise ValueError("Demo jobs fixture version must be an integer") from error
    if version < 1:
        raise ValueError("Demo jobs fixture version must be at least 1")

    jobs = payload.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("Demo jobs fixture must contain at least one job")
    if not all(isinstance(job, dict) for job in jobs):
        raise ValueError("Every demo job must be a JSON object")
    return version, jobs


def _seed_key(user_id: int) -> str:
    return f"{DEMO_JOBS_SEED_KEY_PREFIX}:{user_id}"


def _seeded_version(connection: sqlite3.Connection, user_id: int) -> int:
    row = connection.execute(
        "SELECT value FROM user_preferences WHERE key=?",
        (_seed_key(user_id),),
    ).fetchone()
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def _already_has_job(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    company: str,
    title: str,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1
            FROM jobs
            WHERE user_id=? AND LOWER(company)=LOWER(?) AND LOWER(title)=LOWER(?)
            LIMIT 1
            """,
            (user_id, company, title),
        ).fetchone()
        is not None
    )


def _json_list(job: dict[str, Any], field: str) -> str:
    value = job.get(field, [])
    if value is None:
        value = []
    if not isinstance(value, list):
        raise ValueError(f"Demo job field {field!r} must be a list")
    return json.dumps(value, ensure_ascii=False)


def _insert_job(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    job: dict[str, Any],
) -> int:
    company = str(job.get("company", "")).strip()
    title = str(job.get("title", "")).strip()
    raw_description = str(job.get("raw_description", "")).strip()
    if not company or not title or not raw_description:
        raise ValueError("Demo jobs require company, title, and raw_description")

    values: dict[str, Any] = {field: job.get(field) for field in JOB_FIELDS}
    values["company"] = company
    values["title"] = title
    values["raw_description"] = raw_description
    values["location"] = str(values.get("location") or "")
    values["remote_status"] = str(values.get("remote_status") or "Unclear")
    values["source_url"] = str(values.get("source_url") or "")
    values["currency"] = str(values.get("currency") or "")
    values["pay_period"] = str(values.get("pay_period") or "")
    values["summary"] = str(values.get("summary") or "")
    values["status"] = str(values.get("status") or "Captured")
    values["pay_disclosed"] = int(bool(values.get("pay_disclosed", False)))
    for field in JSON_LIST_FIELDS:
        values[field] = _json_list(job, field)

    cursor = connection.execute(
        """
        INSERT INTO jobs(
            user_id,company,title,location,remote_status,source_url,raw_description,
            pay_min,pay_max,currency,pay_period,pay_disclosed,match_score,summary,
            strong_matches,concerns,missing_qualifications,status,applied_at
        ) VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, ?,
            CASE WHEN ?='Applied' THEN CURRENT_TIMESTAMP ELSE NULL END
        )
        """,
        (
            user_id,
            values["company"],
            values["title"],
            values["location"],
            values["remote_status"],
            values["source_url"],
            values["raw_description"],
            values.get("pay_min"),
            values.get("pay_max"),
            values["currency"],
            values["pay_period"],
            values["pay_disclosed"],
            values.get("match_score"),
            values["summary"],
            values["strong_matches"],
            values["concerns"],
            values["missing_qualifications"],
            values["status"],
            values["status"],
        ),
    )
    job_id = int(cursor.lastrowid)

    events = job.get("events", [])
    if events is None:
        events = []
    if not isinstance(events, list):
        raise ValueError("Demo job events must be a list")
    if not events:
        events = [{"event_type": "Captured"}]
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Demo job events must contain JSON objects")
        event_type = str(event.get("event_type", "")).strip()
        if not event_type:
            raise ValueError("Demo job event_type is required")
        metadata = event.get("metadata", {})
        if metadata is None:
            metadata = {}
        connection.execute(
            """
            INSERT INTO application_events(
                job_id,event_type,details,source,source_ref,metadata
            ) VALUES (?,?,?,?,?,?)
            """,
            (
                job_id,
                event_type,
                str(event.get("details") or ""),
                str(event.get("source") or "manual"),
                event.get("source_ref"),
                json.dumps(metadata, ensure_ascii=False),
            ),
        )

    analysis_runs = job.get("analysis_runs", [])
    if analysis_runs is None:
        analysis_runs = []
    if not isinstance(analysis_runs, list):
        raise ValueError("Demo job analysis_runs must be a list")
    for run in analysis_runs:
        if not isinstance(run, dict):
            raise ValueError("Demo analysis runs must contain JSON objects")
        connection.execute(
            """
            INSERT INTO analysis_runs(job_id,model,prompt_version,raw_result)
            VALUES (?,?,?,?)
            """,
            (
                job_id,
                str(run.get("model") or ""),
                str(run.get("prompt_version") or "brief-v1"),
                json.dumps(run.get("raw_result", {}), ensure_ascii=False),
            ),
        )

    questions = job.get("questions", [])
    if questions is None:
        questions = []
    if not isinstance(questions, list):
        raise ValueError("Demo job questions must be a list")
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError("Demo questions must contain JSON objects")
        question_text = str(question.get("question", "")).strip()
        if not question_text:
            raise ValueError("Demo question text is required")
        submitted_answer = str(question.get("submitted_answer") or "")
        connection.execute(
            """
            INSERT INTO questions(
                job_id,question,suggested_answer,submitted_answer,submitted_at
            ) VALUES (?,?,?,?,CASE WHEN ? <> '' THEN CURRENT_TIMESTAMP ELSE NULL END)
            """,
            (
                job_id,
                question_text,
                str(question.get("suggested_answer") or ""),
                submitted_answer,
                submitted_answer,
            ),
        )

    return job_id


def seed_packaged_demo_jobs(
    connection: sqlite3.Connection,
    fixture_path: str | Path = DEFAULT_DEMO_JOBS_PATH,
) -> int:
    """Seed packaged demo jobs once for the active Ol Sarge account.

    The seed marker is versioned per user. Existing jobs with the same company/title
    are treated as the demo job already being present, which avoids duplicating the
    source records used to build the fixture during development.
    """

    loaded = _load_fixture(Path(fixture_path))
    if loaded is None:
        return 0

    user_id = _active_demo_user_id(connection)
    if user_id is None:
        return 0

    version, jobs = loaded
    if _seeded_version(connection, user_id) >= version:
        return 0

    inserted = 0
    for job in jobs:
        company = str(job.get("company", "")).strip()
        title = str(job.get("title", "")).strip()
        if _already_has_job(connection, user_id=user_id, company=company, title=title):
            continue
        _insert_job(connection, user_id=user_id, job=job)
        inserted += 1

    connection.execute(
        """
        INSERT OR REPLACE INTO user_preferences(key,value)
        VALUES (?,?)
        """,
        (_seed_key(user_id), str(version)),
    )
    return inserted


__all__ = [
    "DEFAULT_DEMO_JOBS_PATH",
    "DEMO_JOBS_FORMAT",
    "DEMO_USER_NAME",
    "seed_packaged_demo_jobs",
]
