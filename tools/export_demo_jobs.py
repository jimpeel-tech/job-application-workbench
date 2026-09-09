from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from jaw.importers.spreadsheet_applications import resolve_user_id
from jaw.paths import database_path

DEFAULT_COMPANIES = ("12th Man Software", "Howdy Technologies")
JSON_FIELDS = ("strong_matches", "concerns", "missing_qualifications")
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


def _decode_json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _fetch_jobs(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    job_ids: list[int],
    companies: list[str],
    export_all: bool,
) -> list[sqlite3.Row]:
    clauses = ["user_id=?"]
    parameters: list[Any] = [user_id]

    selectors: list[str] = []
    if job_ids:
        placeholders = ",".join("?" for _ in job_ids)
        selectors.append(f"id IN ({placeholders})")
        parameters.extend(job_ids)
    if companies:
        placeholders = ",".join("?" for _ in companies)
        selectors.append(f"LOWER(company) IN ({placeholders})")
        parameters.extend(company.casefold() for company in companies)

    if not export_all:
        if not selectors:
            raise ValueError("At least one job selector is required")
        clauses.append(f"({' OR '.join(selectors)})")

    return list(
        connection.execute(
            f"SELECT * FROM jobs WHERE {' AND '.join(clauses)} ORDER BY id",
            parameters,
        )
    )


def _export_events(connection: sqlite3.Connection, job_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT event_type, details, source, source_ref, metadata
        FROM application_events
        WHERE job_id=?
        ORDER BY id
        """,
        (job_id,),
    )
    return [
        {
            "event_type": row["event_type"],
            "details": row["details"],
            "source": row["source"],
            "source_ref": row["source_ref"],
            "metadata": _decode_json(row["metadata"], {}),
        }
        for row in rows
    ]


def _export_analysis_runs(
    connection: sqlite3.Connection,
    job_id: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT model, prompt_version, raw_result
        FROM analysis_runs
        WHERE job_id=?
        ORDER BY id
        """,
        (job_id,),
    )
    return [
        {
            "model": row["model"],
            "prompt_version": row["prompt_version"],
            "raw_result": _decode_json(row["raw_result"], {}),
        }
        for row in rows
    ]


def _export_questions(connection: sqlite3.Connection, job_id: int) -> list[dict[str, str]]:
    rows = connection.execute(
        """
        SELECT question, suggested_answer, submitted_answer
        FROM questions
        WHERE job_id=?
        ORDER BY id
        """,
        (job_id,),
    )
    return [
        {
            "question": row["question"],
            "suggested_answer": row["suggested_answer"],
            "submitted_answer": row["submitted_answer"],
        }
        for row in rows
    ]


def _export_job(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    job = {field: row[field] for field in JOB_FIELDS}
    job["pay_disclosed"] = bool(job["pay_disclosed"])
    for field in JSON_FIELDS:
        job[field] = _decode_json(job[field], [])

    job["events"] = _export_events(connection, int(row["id"]))
    job["analysis_runs"] = _export_analysis_runs(connection, int(row["id"]))
    job["questions"] = _export_questions(connection, int(row["id"]))
    return job


def export_demo_jobs(
    database: Path,
    *,
    user_id: int,
    job_ids: list[int],
    companies: list[str],
    export_all: bool = False,
) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = _fetch_jobs(
            connection,
            user_id=user_id,
            job_ids=job_ids,
            companies=companies,
            export_all=export_all,
        )
        return {
            "format": "jaw-demo-jobs",
            "version": 1,
            "jobs": [_export_job(connection, row) for row in rows],
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Export analyzed JAW jobs into a portable first-run demo fixture. "
            "Database IDs, user IDs, and timestamps are intentionally omitted."
        )
    )
    parser.add_argument(
        "--user",
        default="Ol Sarge",
        help="JAW user account name. Defaults to Ol Sarge.",
    )
    parser.add_argument(
        "--job-id",
        type=int,
        action="append",
        default=[],
        help="Job ID to export. May be specified more than once.",
    )
    parser.add_argument(
        "--company",
        action="append",
        dest="companies",
        help=(
            "Exact company name to export. May be specified more than once. "
            "Defaults to the two packaged demo companies."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export every job owned by the selected user.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=database_path(),
        help="JAW SQLite database path. Defaults to the normal JAW database.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("src/jaw/resources/default-jobs-v1.0.json"),
        help="Fixture output path.",
    )
    args = parser.parse_args()

    target_database = args.database.expanduser().resolve()
    if not target_database.is_file():
        raise SystemExit(f"Database not found: {target_database}")

    user_id = resolve_user_id(target_database, args.user)
    companies = (
        list(args.companies)
        if args.companies
        else ([] if args.job_id or args.all else list(DEFAULT_COMPANIES))
    )

    fixture = export_demo_jobs(
        target_database,
        user_id=user_id,
        job_ids=args.job_id,
        companies=companies,
        export_all=args.all,
    )
    jobs = fixture["jobs"]
    if not jobs:
        selectors = "all jobs" if args.all else ", ".join(companies) or str(args.job_id)
        raise SystemExit(f"No matching jobs found for {args.user}: {selectors}")

    if not args.all and companies:
        found = {str(job["company"]).casefold() for job in jobs}
        missing = [company for company in companies if company.casefold() not in found]
        if missing:
            raise SystemExit("Missing requested demo job(s): " + ", ".join(missing))

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"User: {args.user} (id={user_id})")
    print(f"Database: {target_database}")
    print(f"Exported jobs: {len(jobs)}")
    for job in jobs:
        print(f"  - {job['company']} — {job['title']} [{job['status']}]")
    print(f"Fixture: {output}")


if __name__ == "__main__":
    main()
