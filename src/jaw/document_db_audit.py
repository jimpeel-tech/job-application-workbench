"""Inspect JAW document persistence without initializing or mutating the database."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from .paths import database_path
from .persistence.schema import LEGACY_DOCUMENT_TABLES

WORKBENCH_TABLES = (
    "document_workbench_documents",
    "document_workbench_resources",
    "document_workbench_edges",
    "document_workbench_buffers",
)


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    }


def _count(connection: sqlite3.Connection, table: str) -> int:
    # Names are drawn only from sqlite_master / constants above, never user input.
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def audit(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Database not found: {path}")
    connection = sqlite3.connect(path)
    try:
        tables = _tables(connection)
        missing_workbench_tables = sorted(set(WORKBENCH_TABLES) - tables)
        workbench = {
            table: _count(connection, table)
            for table in WORKBENCH_TABLES
            if table in tables
        }
        resources: dict[str, int] = {}
        if "document_workbench_resources" in tables:
            resources = {
                str(kind): int(count)
                for kind, count in connection.execute(
                    """
                    SELECT kind, COUNT(*)
                    FROM document_workbench_resources
                    GROUP BY kind
                    ORDER BY kind
                    """
                )
            }
        legacy = {
            table: _count(connection, table)
            for table in LEGACY_DOCUMENT_TABLES
            if table in tables
        }
        known = set(WORKBENCH_TABLES) | set(LEGACY_DOCUMENT_TABLES)
        discovered_document_tables = sorted(
            table
            for table in tables
            if (table.startswith("document") or table.startswith("generated_document"))
            and table not in known
        )
        extra = {table: _count(connection, table) for table in discovered_document_tables}
        foreign_keys = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
        return {
            "path": str(path.resolve()),
            "workbench": workbench,
            "missing_workbench_tables": missing_workbench_tables,
            "resources": resources,
            "legacy": legacy,
            "extra_document_tables": extra,
            "foreign_key_violations": foreign_keys,
        }
    finally:
        connection.close()


def workbench_is_empty(result: dict[str, object]) -> bool:
    counts = result.get("workbench") or {}
    missing = result.get("missing_workbench_tables") or []
    return (
        isinstance(counts, dict)
        and set(counts) == set(WORKBENCH_TABLES)
        and all(int(value) == 0 for value in counts.values())
        and isinstance(missing, list)
        and not missing
    )


def document_store_is_clean(result: dict[str, object]) -> bool:
    legacy = result.get("legacy") or {}
    extra = result.get("extra_document_tables") or {}
    violations = result.get("foreign_key_violations") or []
    return (
        workbench_is_empty(result)
        and isinstance(legacy, dict)
        and not legacy
        and isinstance(extra, dict)
        and not extra
        and isinstance(violations, list)
        and not violations
    )


def _print_group(title: str, values: dict[str, int]) -> None:
    print(title)
    if not values:
        print("  (none)")
        return
    width = max(len(key) for key in values)
    for key, value in values.items():
        print(f"  {key:<{width}}  {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit JAW Workbench SQLite data")
    parser.add_argument("--database", type=Path, default=database_path())
    parser.add_argument(
        "--expect-empty",
        action="store_true",
        help=(
            "exit non-zero unless the complete Workbench schema exists with zero rows, "
            "retired Document tables are gone, and foreign keys are clean"
        ),
    )
    args = parser.parse_args()

    result = audit(args.database.expanduser().resolve())
    print(f"Database: {result['path']}")
    _print_group("Workbench tables:", result["workbench"])  # type: ignore[arg-type]
    missing = result["missing_workbench_tables"]
    if isinstance(missing, list) and missing:
        print("Missing Workbench tables:")
        for table in missing:
            print(f"  {table}")
    else:
        print("Missing Workbench tables: (none)")
    _print_group("Workbench resources by kind:", result["resources"])  # type: ignore[arg-type]
    _print_group("Retired document tables still present:", result["legacy"])  # type: ignore[arg-type]
    _print_group("Other document-like tables:", result["extra_document_tables"])  # type: ignore[arg-type]
    violations = result["foreign_key_violations"]
    print(f"Foreign key violations: {len(violations) if isinstance(violations, list) else '?'}")

    clean = document_store_is_clean(result)
    if args.expect_empty and not clean:
        print("RESULT: Document store is NOT clean")
        return 1
    print("RESULT: Document store is clean" if clean else "RESULT: Document store contains data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
