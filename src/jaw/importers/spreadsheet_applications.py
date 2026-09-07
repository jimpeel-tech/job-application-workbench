from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..database import JobDatabase
from ..persistence import UserRepository

IMPORT_EVENT_TYPE = "Imported"
IMPORT_EVENT_PREFIX = "Spreadsheet fixture: "


@dataclass(frozen=True)
class HistoricalApplication:
    fixture_id: str
    company: str
    title: str
    location: str
    remote_status: str
    source_url: str
    raw_description: str
    pay_min: float | None
    pay_max: float | None
    currency: str
    pay_period: str
    applied_at: str
    application_questions: tuple[str, ...]

    @property
    def import_marker(self) -> str:
        return f"{IMPORT_EVENT_PREFIX}{self.fixture_id}"


@dataclass(frozen=True)
class ImportResult:
    approved: int
    imported: int
    already_imported: int
    ignored_unapproved: int
    dry_run: bool


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _optional_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _application_from_files(
    expected_path: Path,
    capture_path: Path,
) -> HistoricalApplication | None:
    expected = _read_json(expected_path)
    capture = _read_json(capture_path)
    manifest = capture.get("manifest", {})

    if str(manifest.get("status", "")).strip().lower() != "approved":
        return None

    fixture_id = str(expected.get("fixture_id", "")).strip()
    capture_fixture_id = str(manifest.get("fixture_id", "")).strip()
    if not fixture_id:
        raise ValueError(f"Missing fixture_id in {expected_path}")
    if capture_fixture_id != fixture_id:
        raise ValueError(
            f"Fixture id mismatch for {expected_path.name}: "
            f"expected={fixture_id!r}, capture={capture_fixture_id!r}"
        )

    source = manifest.get("source", {})
    applied_at = str(source.get("date", "")).strip()
    if not applied_at:
        raise ValueError(f"Missing spreadsheet application date for {fixture_id}")
    try:
        date.fromisoformat(applied_at)
    except ValueError as exc:
        raise ValueError(
            f"Invalid spreadsheet application date for {fixture_id}: {applied_at!r}"
        ) from exc

    company = str(expected.get("company", "")).strip()
    title = str(expected.get("title", "")).strip()
    raw_description = str(expected.get("raw_description", "")).strip()
    if not company or not title or not raw_description:
        raise ValueError(
            f"Approved fixture {fixture_id} must contain company, title, and raw_description"
        )

    questions = tuple(
        str(item).strip()
        for item in expected.get("application_questions", [])
        if str(item).strip()
    )

    return HistoricalApplication(
        fixture_id=fixture_id,
        company=company,
        title=title,
        location=str(expected.get("location", "")).strip(),
        remote_status=str(expected.get("remote_status", "")).strip() or "Unclear",
        source_url=str(expected.get("source_url", "")).strip(),
        raw_description=raw_description,
        pay_min=_optional_number(expected.get("pay_min")),
        pay_max=_optional_number(expected.get("pay_max")),
        currency=str(expected.get("currency", "")).strip(),
        pay_period=str(expected.get("pay_period", "")).strip(),
        applied_at=applied_at,
        application_questions=questions,
    )


def load_approved_applications(
    source_dir: Path,
) -> tuple[list[HistoricalApplication], int]:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Spreadsheet fixture directory not found: {source_dir}")

    applications: list[HistoricalApplication] = []
    ignored_unapproved = 0
    expected_paths = sorted(source_dir.glob("*.expected.json"))
    if not expected_paths:
        raise FileNotFoundError(f"No *.expected.json fixtures found in {source_dir}")

    for expected_path in expected_paths:
        fixture_id = expected_path.name.removesuffix(".expected.json")
        capture_path = source_dir / f"{fixture_id}.capture.json"
        if not capture_path.is_file():
            raise FileNotFoundError(
                f"Missing capture manifest for {expected_path.name}: {capture_path.name}"
            )
        application = _application_from_files(expected_path, capture_path)
        if application is None:
            ignored_unapproved += 1
            continue
        applications.append(application)

    return applications, ignored_unapproved


def resolve_user_id(database_path: Path, user_name: str) -> int:
    requested = str(user_name or "").strip()
    if not requested:
        raise ValueError("User name is required")

    repository = UserRepository(database_path)
    with repository.transaction() as session:
        session.initialize_schema()
        users = session.list_users()

    exact = [user for user in users if user.name == requested]
    if len(exact) == 1:
        return exact[0].id

    folded = [user for user in users if user.name.casefold() == requested.casefold()]
    if len(folded) == 1:
        return folded[0].id
    if len(folded) > 1:
        raise ValueError(f"User name is ambiguous: {requested!r}")

    available = ", ".join(user.name for user in users) or "<none>"
    raise ValueError(f"User not found: {requested!r}. Available users: {available}")


def _existing_import_markers(
    database: JobDatabase,
    user_id: int,
) -> set[str]:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT e.details
            FROM application_events e
            JOIN jobs j ON j.id=e.job_id
            WHERE j.user_id=? AND e.event_type=? AND e.details LIKE ?
            """,
            (user_id, IMPORT_EVENT_TYPE, f"{IMPORT_EVENT_PREFIX}%"),
        ).fetchall()
    return {str(row["details"]) for row in rows}


def _insert_application(
    connection: Any,
    user_id: int,
    application: HistoricalApplication,
) -> int:
    pay_disclosed = int(
        application.pay_min is not None or application.pay_max is not None
    )
    cursor = connection.execute(
        """
        INSERT INTO jobs(
            user_id,company,title,location,remote_status,source_url,raw_description,
            pay_min,pay_max,currency,pay_period,pay_disclosed,status,applied_at,
            created_at,updated_at
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            application.company,
            application.title,
            application.location,
            application.remote_status,
            application.source_url,
            application.raw_description,
            application.pay_min,
            application.pay_max,
            application.currency,
            application.pay_period,
            pay_disclosed,
            "Applied",
            application.applied_at,
            application.applied_at,
            application.applied_at,
        ),
    )
    job_id = int(cursor.lastrowid)

    connection.execute(
        """
        INSERT INTO application_events(job_id,event_type,details,occurred_at)
        VALUES (?,?,?,?)
        """,
        (
            job_id,
            IMPORT_EVENT_TYPE,
            application.import_marker,
            application.applied_at,
        ),
    )
    connection.execute(
        """
        INSERT INTO application_events(job_id,event_type,details,occurred_at)
        VALUES (?,?,?,?)
        """,
        (
            job_id,
            "Applied",
            "Historical spreadsheet application",
            application.applied_at,
        ),
    )

    for question in application.application_questions:
        connection.execute(
            """
            INSERT INTO questions(job_id,question,created_at)
            VALUES (?,?,?)
            """,
            (job_id, question, application.applied_at),
        )

    return job_id


def import_spreadsheet_applications(
    database: JobDatabase,
    *,
    user_id: int,
    source_dir: Path,
    apply: bool = False,
) -> ImportResult:
    applications, ignored_unapproved = load_approved_applications(source_dir)
    existing_markers = _existing_import_markers(database, user_id)
    pending = [
        application
        for application in applications
        if application.import_marker not in existing_markers
    ]
    already_imported = len(applications) - len(pending)

    if apply and pending:
        with database.connect() as connection:
            for application in pending:
                _insert_application(connection, user_id, application)

    return ImportResult(
        approved=len(applications),
        imported=len(pending) if apply else 0,
        already_imported=already_imported,
        ignored_unapproved=ignored_unapproved,
        dry_run=not apply,
    )


__all__ = [
    "HistoricalApplication",
    "ImportResult",
    "import_spreadsheet_applications",
    "load_approved_applications",
    "resolve_user_id",
]
