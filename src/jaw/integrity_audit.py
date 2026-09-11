"""Read-only release integrity audit for JAW's SQLite database."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .paths import DATABASE_SCHEMA_VERSION, database_path
from .persistence.document_workbench import DOCUMENT_WORKBENCH_SCHEMA
from .persistence.schema import LEGACY_DOCUMENT_TABLES, SCHEMA
from .persistence.user_repository import USER_SCHEMA

CORE_TABLES = (
    "jobs",
    "application_events",
    "outlook_messages",
    "outlook_sync_state",
    "questions",
    "analysis_runs",
    "capture_sessions",
    "capture_events",
)
USER_TABLES = ("user_accounts", "user_preferences")
WORKBENCH_TABLES = (
    "document_workbench_resources",
    "document_workbench_documents",
    "document_workbench_edges",
    "document_workbench_buffers",
)
REQUIRED_TABLES = CORE_TABLES + USER_TABLES + WORKBENCH_TABLES

_JSON_OBJECT_COLUMNS = (
    ("user_accounts", "id", "data_json"),
    ("application_events", "id", "metadata"),
    ("outlook_messages", "id", "metadata"),
    ("capture_events", "id", "metadata"),
    ("analysis_runs", "id", "raw_result"),
    ("document_workbench_resources", "id", "settings"),
)
_JSON_ARRAY_COLUMNS = (
    ("jobs", "id", "strong_matches"),
    ("jobs", "id", "concerns"),
    ("jobs", "id", "missing_qualifications"),
)
_WORKBENCH_AUDIT_COLUMNS = {
    "document_workbench_resources": {
        "id",
        "user_id",
        "kind",
        "name",
        "symbol",
        "owner_id",
        "content",
        "content_hash",
    },
    "document_workbench_documents": {"resource_id", "template_id"},
    "document_workbench_edges": {"parent_id", "child_id", "edge_kind", "symbol"},
    "document_workbench_buffers": {"user_id", "resource_id", "cursor_start", "cursor_end"},
}


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    }


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{table}")')
    }


def _expected_columns() -> dict[str, set[str]]:
    with sqlite3.connect(":memory:") as connection:
        connection.executescript(SCHEMA)
        connection.executescript(USER_SCHEMA)
        connection.executescript(DOCUMENT_WORKBENCH_SCHEMA)
        return {
            table: _columns(connection, table)
            for table in REQUIRED_TABLES
        }


def _actual_columns(
    connection: sqlite3.Connection,
    tables: set[str],
) -> dict[str, set[str]]:
    return {
        table: _columns(connection, table)
        for table in REQUIRED_TABLES
        if table in tables
    }


def _missing_columns(actual: dict[str, set[str]]) -> list[str]:
    expected = _expected_columns()
    return sorted(
        f"{table}.{column}"
        for table, expected_columns in expected.items()
        if table in actual
        for column in expected_columns - actual[table]
    )


def _json_violations(
    connection: sqlite3.Connection,
    actual_columns: dict[str, set[str]],
) -> list[str]:
    violations: list[str] = []
    specs = [
        *((table, key, column, dict) for table, key, column in _JSON_OBJECT_COLUMNS),
        *((table, key, column, list) for table, key, column in _JSON_ARRAY_COLUMNS),
    ]
    for table, key_column, value_column, expected_type in specs:
        columns = actual_columns.get(table, set())
        if not {key_column, value_column}.issubset(columns):
            continue
        rows = connection.execute(
            f'SELECT "{key_column}", "{value_column}" FROM "{table}"'
        )
        for row_key, raw_value in rows:
            try:
                decoded = json.loads(str(raw_value))
            except (TypeError, ValueError):
                violations.append(
                    f"{table}[{row_key}].{value_column}: invalid JSON"
                )
                continue
            if not isinstance(decoded, expected_type):
                violations.append(
                    f"{table}[{row_key}].{value_column}: expected "
                    f"{expected_type.__name__}, found {type(decoded).__name__}"
                )
    return violations


def _user_violations(
    connection: sqlite3.Connection,
    actual_columns: dict[str, set[str]],
) -> list[str]:
    if not {"id"}.issubset(actual_columns.get("user_accounts", set())):
        return []
    if not {"key", "value"}.issubset(actual_columns.get("user_preferences", set())):
        return []

    users = {
        int(row[0])
        for row in connection.execute("SELECT id FROM user_accounts")
    }
    row = connection.execute(
        "SELECT value FROM user_preferences WHERE key='active_user_id'"
    ).fetchone()
    if row is None:
        return []
    try:
        active_user_id = int(row[0])
    except (TypeError, ValueError):
        return ["user_preferences.active_user_id: value is not an integer"]
    if active_user_id not in users:
        return [
            f"user_preferences.active_user_id: user {active_user_id} does not exist"
        ]
    return []


def _workbench_violations(
    connection: sqlite3.Connection,
    actual_columns: dict[str, set[str]],
) -> list[str]:
    if any(
        not columns.issubset(actual_columns.get(table, set()))
        for table, columns in _WORKBENCH_AUDIT_COLUMNS.items()
    ):
        return []

    violations: list[str] = []
    resources = {
        str(row["id"]): dict(row)
        for row in connection.execute(
            "SELECT id,user_id,kind,name,symbol,owner_id,content,content_hash "
            "FROM document_workbench_resources"
        )
    }
    documents = {
        str(row["resource_id"]): dict(row)
        for row in connection.execute(
            "SELECT resource_id,template_id FROM document_workbench_documents"
        )
    }

    for resource_id, resource in resources.items():
        content = str(resource["content"] or "")
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if str(resource["content_hash"] or "") != expected_hash:
            violations.append(f"resource {resource_id}: content_hash does not match content")

        kind = str(resource["kind"])
        if kind in {"section", "function"} and str(resource["name"] or ""):
            violations.append(f"resource {resource_id}: {kind} resource has a display name")

        owner_id = resource["owner_id"]
        if owner_id is not None:
            owner = resources.get(str(owner_id))
            if owner is not None and int(owner["user_id"]) != int(resource["user_id"]):
                violations.append(
                    f"resource {resource_id}: owner {owner_id} belongs to another user"
                )

        if kind == "document" and resource_id not in documents:
            violations.append(f"resource {resource_id}: document resource has no document row")

    for document_id, document in documents.items():
        resource = resources.get(document_id)
        template_id = str(document["template_id"])
        template = resources.get(template_id)
        if resource is not None and str(resource["kind"]) != "document":
            violations.append(
                f"document row {document_id}: resource kind is {resource['kind']}, expected document"
            )
        if template is not None and str(template["kind"]) != "template":
            violations.append(
                f"document {document_id}: template {template_id} is kind "
                f"{template['kind']}, expected template"
            )
        if resource is not None and template is not None:
            if int(resource["user_id"]) != int(template["user_id"]):
                violations.append(
                    f"document {document_id}: template {template_id} belongs to another user"
                )

    for edge in connection.execute(
        "SELECT parent_id,child_id,edge_kind,symbol FROM document_workbench_edges"
    ):
        parent_id = str(edge["parent_id"])
        child_id = str(edge["child_id"])
        edge_kind = str(edge["edge_kind"])
        parent = resources.get(parent_id)
        child = resources.get(child_id)
        if not str(edge["symbol"] or "").strip():
            violations.append(f"edge {parent_id}->{child_id}: symbol is empty")
        if parent is not None and child is not None:
            if int(parent["user_id"]) != int(child["user_id"]):
                violations.append(
                    f"edge {parent_id}->{child_id}: resources belong to different users"
                )
            expected_child = edge_kind
            if str(child["kind"]) != expected_child:
                violations.append(
                    f"edge {parent_id}->{child_id}: child kind is {child['kind']}, "
                    f"expected {expected_child}"
                )
            expected_parent = {"section": "document", "function": "section"}.get(edge_kind)
            if expected_parent and str(parent["kind"]) != expected_parent:
                violations.append(
                    f"edge {parent_id}->{child_id}: parent kind is {parent['kind']}, "
                    f"expected {expected_parent}"
                )

    for buffer_row in connection.execute(
        "SELECT user_id,resource_id,cursor_start,cursor_end FROM document_workbench_buffers"
    ):
        resource_id = str(buffer_row["resource_id"])
        resource = resources.get(resource_id)
        if resource is not None and int(buffer_row["user_id"]) != int(resource["user_id"]):
            violations.append(f"buffer {resource_id}: buffer user does not own resource")
        if int(buffer_row["cursor_start"]) < 0 or int(buffer_row["cursor_end"]) < 0:
            violations.append(f"buffer {resource_id}: cursor position is negative")

    return violations


def audit(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Database not found: {resolved}")

    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = _tables(connection)
        actual_columns = _actual_columns(connection, tables)
        integrity_check = [
            str(row[0]) for row in connection.execute("PRAGMA integrity_check")
        ]
        schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        foreign_keys = [
            tuple(row) for row in connection.execute("PRAGMA foreign_key_check")
        ]
        return {
            "path": str(resolved),
            "schema_version": schema_version,
            "expected_schema_version": DATABASE_SCHEMA_VERSION,
            "missing_tables": sorted(set(REQUIRED_TABLES) - tables),
            "missing_columns": _missing_columns(actual_columns),
            "legacy_tables": sorted(set(LEGACY_DOCUMENT_TABLES) & tables),
            "integrity_check": integrity_check,
            "foreign_key_violations": foreign_keys,
            "json_violations": _json_violations(connection, actual_columns),
            "user_violations": _user_violations(connection, actual_columns),
            "workbench_violations": _workbench_violations(connection, actual_columns),
        }
    finally:
        connection.close()


def integrity_is_clean(result: dict[str, Any]) -> bool:
    return (
        result.get("schema_version") == result.get("expected_schema_version")
        and result.get("integrity_check") == ["ok"]
        and not result.get("missing_tables")
        and not result.get("missing_columns")
        and not result.get("legacy_tables")
        and not result.get("foreign_key_violations")
        and not result.get("json_violations")
        and not result.get("user_violations")
        and not result.get("workbench_violations")
    )


def _print_issues(title: str, issues: list[Any]) -> None:
    print(f"{title}: {len(issues)}")
    for issue in issues:
        print(f"  - {issue}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit JAW SQLite integrity")
    parser.add_argument("--database", type=Path, default=database_path())
    args = parser.parse_args()

    result = audit(args.database)
    print(f"Database: {result['path']}")
    print(
        "Schema version: "
        f"{result['schema_version']} (expected {result['expected_schema_version']})"
    )
    print(f"SQLite integrity: {', '.join(result['integrity_check'])}")
    _print_issues("Missing required tables", result["missing_tables"])
    _print_issues("Missing required columns", result["missing_columns"])
    _print_issues("Retired document tables", result["legacy_tables"])
    _print_issues("Foreign key violations", result["foreign_key_violations"])
    _print_issues("JSON violations", result["json_violations"])
    _print_issues("User-state violations", result["user_violations"])
    _print_issues("Workbench semantic violations", result["workbench_violations"])

    clean = integrity_is_clean(result)
    print("RESULT: Integrity audit passed" if clean else "RESULT: Integrity audit FAILED")
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
