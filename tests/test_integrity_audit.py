from __future__ import annotations

import sqlite3
from pathlib import Path

from jaw.database import JobDatabase
from jaw.integrity_audit import audit, integrity_is_clean
from jaw.userdata import UserDataStore


def _initialized_database(path: Path) -> tuple[JobDatabase, int]:
    store = UserDataStore(path)
    state = store.read()
    database = JobDatabase(path, seed_demo=False)
    return database, int(state["active_user_id"])


def test_initialized_database_passes_integrity_audit(tmp_path: Path) -> None:
    path = tmp_path / "jaw.db"
    _initialized_database(path)

    result = audit(path)

    assert result["integrity_check"] == ["ok"]
    assert result["schema_version"] == result["expected_schema_version"]
    assert result["missing_tables"] == []
    assert result["missing_columns"] == []
    assert result["legacy_tables"] == []
    assert result["foreign_key_violations"] == []
    assert result["json_violations"] == []
    assert result["user_violations"] == []
    assert result["workbench_violations"] == []
    assert integrity_is_clean(result) is True


def test_partial_schema_is_reported_without_crashing(tmp_path: Path) -> None:
    path = tmp_path / "partial.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY)")
        connection.execute("PRAGMA user_version = 7")

    result = audit(path)

    assert "application_events" in result["missing_tables"]
    assert "jobs.strong_matches" in result["missing_columns"]
    assert integrity_is_clean(result) is False


def test_invalid_user_json_fails_integrity_audit(tmp_path: Path) -> None:
    path = tmp_path / "jaw.db"
    _database, user_id = _initialized_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE user_accounts SET data_json=? WHERE id=?",
            ("{broken", user_id),
        )

    result = audit(path)

    assert any("user_accounts" in issue for issue in result["json_violations"])
    assert integrity_is_clean(result) is False


def test_invalid_active_user_preference_fails_integrity_audit(tmp_path: Path) -> None:
    path = tmp_path / "jaw.db"
    _initialized_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO user_preferences(key,value) VALUES (?,?)",
            ("active_user_id", "999999"),
        )

    result = audit(path)

    assert result["user_violations"] == [
        "user_preferences.active_user_id: user 999999 does not exist"
    ]
    assert integrity_is_clean(result) is False


def test_document_template_kind_is_checked_beyond_foreign_keys(tmp_path: Path) -> None:
    path = tmp_path / "jaw.db"
    database, user_id = _initialized_database(path)
    repository = database.document_workbench_repository
    template = repository.create_resource(
        user_id,
        "template",
        name="Resume Template",
        symbol="resume_template",
    )
    section = repository.create_resource(
        user_id,
        "section",
        symbol="summary",
    )
    document = repository.create_document(
        user_id,
        "Resume",
        template["id"],
        output_pattern="Resume.pdf",
    )
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "UPDATE document_workbench_documents SET template_id=? WHERE resource_id=?",
            (section["id"], document["id"]),
        )

    result = audit(path)

    assert result["foreign_key_violations"] == []
    assert any(
        "expected template" in issue for issue in result["workbench_violations"]
    )
    assert integrity_is_clean(result) is False


def test_workbench_content_hash_corruption_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "jaw.db"
    database, user_id = _initialized_database(path)
    resource = database.document_workbench_repository.create_resource(
        user_id,
        "template",
        name="Template",
        symbol="template",
        content="Original content",
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE document_workbench_resources SET content_hash=? WHERE id=?",
            ("not-the-real-hash", resource["id"]),
        )

    result = audit(path)

    assert any(
        "content_hash does not match content" in issue
        for issue in result["workbench_violations"]
    )
    assert integrity_is_clean(result) is False


def test_invalid_workbench_edge_shape_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "jaw.db"
    database, user_id = _initialized_database(path)
    repository = database.document_workbench_repository
    template = repository.create_resource(
        user_id,
        "template",
        name="Template",
        symbol="template",
    )
    document = repository.create_document(
        user_id,
        "Resume",
        template["id"],
        output_pattern="Resume.pdf",
    )
    function = repository.create_resource(user_id, "function", symbol="csv")
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO document_workbench_edges
                (parent_id,child_id,edge_kind,symbol,sort_order)
            VALUES (?,?,?,?,?)
            """,
            (document["id"], function["id"], "section", "bad_edge", 0),
        )

    result = audit(path)

    assert result["foreign_key_violations"] == []
    assert any("child kind is function" in issue for issue in result["workbench_violations"])
    assert integrity_is_clean(result) is False
