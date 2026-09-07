from __future__ import annotations

import sqlite3
from pathlib import Path

from jaw.database import JobDatabase
from jaw.document_db_audit import audit, document_store_is_clean, workbench_is_empty
from jaw.persistence.schema import LEGACY_DOCUMENT_TABLES


def test_fresh_database_has_only_empty_workbench_document_store(tmp_path: Path) -> None:
    path = tmp_path / "jaw.db"
    JobDatabase(path)

    result = audit(path)

    assert workbench_is_empty(result) is True
    assert result["missing_workbench_tables"] == []
    assert result["legacy"] == {}
    assert result["extra_document_tables"] == {}
    assert result["foreign_key_violations"] == []
    assert document_store_is_clean(result) is True


def test_uninitialized_sqlite_file_is_not_a_clean_workbench_store(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()

    result = audit(path)

    assert workbench_is_empty(result) is False
    assert set(result["missing_workbench_tables"]) == {
        "document_workbench_documents",
        "document_workbench_resources",
        "document_workbench_edges",
        "document_workbench_buffers",
    }
    assert document_store_is_clean(result) is False


def test_workbench_document_data_makes_expect_empty_condition_false(tmp_path: Path) -> None:
    path = tmp_path / "jaw.db"
    database = JobDatabase(path)
    repository = database.document_workbench_repository
    template = repository.create_resource(
        1,
        "template",
        name="Template",
        symbol="template",
        visibility="global",
        content="{{ section }}",
    )
    repository.create_document(
        1,
        "Resume",
        template["id"],
        output_pattern="Resume.pdf",
    )

    result = audit(path)

    assert workbench_is_empty(result) is False
    assert document_store_is_clean(result) is False
    assert result["resources"] == {"document": 1, "template": 1}


def test_schema_migration_removes_every_retired_document_table(tmp_path: Path) -> None:
    path = tmp_path / "jaw.db"
    with sqlite3.connect(path) as connection:
        for table in LEGACY_DOCUMENT_TABLES:
            connection.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)')

    before = audit(path)
    assert set(before["legacy"]) == set(LEGACY_DOCUMENT_TABLES)
    assert document_store_is_clean(before) is False

    JobDatabase(path)
    after = audit(path)

    assert after["missing_workbench_tables"] == []
    assert after["legacy"] == {}
    assert document_store_is_clean(after) is True
