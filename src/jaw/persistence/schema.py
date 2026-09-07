from __future__ import annotations

import sqlite3

from ..paths import DATABASE_SCHEMA_VERSION

# These tables belonged to the retired Document Studio and intermediate
# Document Engine models. Workbench persistence is initialized independently by
# DocumentWorkbenchRepository and is now the only Document source of truth.
LEGACY_DOCUMENT_TABLES = (
    # Generated-document history / Studio children first.
    "generated_document_blocks",
    "generated_documents",
    "document_generation_profiles",
    "document_content_template_blocks",
    "document_content_templates",
    "document_content_block_expressions",
    "document_content_blocks",
    "document_blueprint_fields",
    "document_blueprints",
    "document_render_templates",
    "document_studio_state",
    # Intermediate Document Engine graph children first.
    "document_functions",
    "document_section_placements",
    "documents",
    "document_sections",
    "document_templates",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 0,
    company TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    remote_status TEXT NOT NULL DEFAULT 'Unclear',
    source_url TEXT NOT NULL DEFAULT '',
    raw_description TEXT NOT NULL,
    pay_min REAL,
    pay_max REAL,
    currency TEXT NOT NULL DEFAULT '',
    pay_period TEXT NOT NULL DEFAULT '',
    pay_disclosed INTEGER NOT NULL DEFAULT 0,
    match_score INTEGER,
    summary TEXT NOT NULL DEFAULT '',
    strong_matches TEXT NOT NULL DEFAULT '[]',
    concerns TEXT NOT NULL DEFAULT '[]',
    missing_qualifications TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'Captured',
    applied_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS application_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    source_ref TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outlook_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 0,
    message_id TEXT NOT NULL,
    internet_message_id TEXT NOT NULL DEFAULT '',
    received_at TEXT NOT NULL DEFAULT '',
    sender TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    classification TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    classification_confidence REAL NOT NULL DEFAULT 0,
    match_confidence REAL NOT NULL DEFAULT 0,
    decision TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id,message_id)
);

CREATE TABLE IF NOT EXISTS outlook_sync_state (
    user_id INTEGER PRIMARY KEY,
    last_sync_at TEXT,
    last_error TEXT NOT NULL DEFAULT '',
    last_scanned INTEGER NOT NULL DEFAULT 0,
    last_updated INTEGER NOT NULL DEFAULT 0,
    last_categorized INTEGER NOT NULL DEFAULT 0,
    last_review INTEGER NOT NULL DEFAULT 0,
    last_ignored INTEGER NOT NULL DEFAULT 0,
    last_skipped INTEGER NOT NULL DEFAULT 0,
    last_errors INTEGER NOT NULL DEFAULT 0,
    last_truncated INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    suggested_answer TEXT NOT NULL DEFAULT '',
    submitted_answer TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    raw_result TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS capture_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    phase TEXT NOT NULL DEFAULT 'job_capture',
    job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS capture_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES capture_sessions(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'unclassified',
    classification_status TEXT NOT NULL DEFAULT 'pending',
    job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_title ON jobs(title);
CREATE INDEX IF NOT EXISTS idx_jobs_match ON jobs(match_score);
CREATE INDEX IF NOT EXISTS idx_questions_job ON questions(job_id);
CREATE INDEX IF NOT EXISTS idx_capture_sessions_user ON capture_sessions(user_id,status);
CREATE INDEX IF NOT EXISTS idx_capture_events_session ON capture_events(session_id,id);
CREATE INDEX IF NOT EXISTS idx_outlook_messages_user_received
    ON outlook_messages(user_id,received_at);
CREATE INDEX IF NOT EXISTS idx_outlook_messages_job ON outlook_messages(job_id);
"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create/migrate the active tracker schema and remove retired Document models."""
    _drop_legacy_document_tables(connection)
    connection.executescript(SCHEMA)

    columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)")}
    if "applied_at" not in columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN applied_at TEXT")
    if "user_id" not in columns:
        connection.execute(
            "ALTER TABLE jobs ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0"
        )
    _ensure_column(
        connection,
        "application_events",
        "source",
        "TEXT NOT NULL DEFAULT 'manual'",
    )
    _ensure_column(connection, "application_events", "source_ref", "TEXT")
    _ensure_column(
        connection,
        "application_events",
        "metadata",
        "TEXT NOT NULL DEFAULT '{}'",
    )
    _ensure_column(
        connection,
        "capture_sessions",
        "phase",
        "TEXT NOT NULL DEFAULT 'job_capture'",
    )
    _ensure_column(
        connection,
        "capture_sessions",
        "job_id",
        "INTEGER REFERENCES jobs(id) ON DELETE SET NULL",
    )
    _ensure_column(
        connection,
        "capture_events",
        "content_type",
        "TEXT NOT NULL DEFAULT 'unclassified'",
    )
    _ensure_column(
        connection,
        "capture_events",
        "classification_status",
        "TEXT NOT NULL DEFAULT 'pending'",
    )
    _ensure_column(
        connection,
        "capture_events",
        "job_id",
        "INTEGER REFERENCES jobs(id) ON DELETE SET NULL",
    )
    _ensure_column(
        connection,
        "capture_events",
        "metadata",
        "TEXT NOT NULL DEFAULT '{}'",
    )
    connection.execute(
        """
        UPDATE jobs
        SET applied_at = (
            SELECT MIN(occurred_at)
            FROM application_events
            WHERE job_id = jobs.id AND event_type = 'Applied'
        )
        WHERE applied_at IS NULL
        """
    )
    connection.execute("UPDATE jobs SET status='Reviewing' WHERE status='Analyzed'")
    connection.execute(f"PRAGMA user_version = {DATABASE_SCHEMA_VERSION}")


def _drop_legacy_document_tables(connection: sqlite3.Connection) -> None:
    for table in LEGACY_DOCUMENT_TABLES:
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    name: str,
    declaration: str,
) -> None:
    columns = {
        row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
    }
    if name not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


__all__ = ["LEGACY_DOCUMENT_TABLES", "SCHEMA", "_ensure_column", "initialize_schema"]
