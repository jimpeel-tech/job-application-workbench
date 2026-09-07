from __future__ import annotations

import sqlite3
from pathlib import Path

from jaw.database import JobDatabase

_INTERMEDIATE_EDGE_SCHEMA = """
CREATE TABLE document_workbench_resources (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    symbol TEXT NOT NULL DEFAULT '',
    visibility TEXT NOT NULL DEFAULT 'private',
    state TEXT NOT NULL DEFAULT 'active',
    owner_id TEXT,
    content TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    settings TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE document_workbench_edges (
    id TEXT PRIMARY KEY,
    parent_id TEXT NOT NULL REFERENCES document_workbench_resources(id) ON DELETE CASCADE,
    child_id TEXT NOT NULL REFERENCES document_workbench_resources(id) ON DELETE CASCADE,
    edge_kind TEXT NOT NULL,
    symbol TEXT NOT NULL COLLATE NOCASE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(parent_id,child_id),
    UNIQUE(parent_id,symbol)
);
"""


def test_intermediate_reference_schema_migrates_without_losing_reference_jid(
    tmp_path: Path,
) -> None:
    path = tmp_path / "jaw.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(_INTERMEDIATE_EDGE_SCHEMA)
        connection.execute(
            """
            INSERT INTO document_workbench_resources
                (id,user_id,kind,name,symbol,visibility,state,content,content_hash,settings)
            VALUES ('doc_existing',1,'document','Document','document','private','active','','','{}')
            """
        )
        connection.execute(
            """
            INSERT INTO document_workbench_resources
                (id,user_id,kind,name,symbol,visibility,state,owner_id,content,content_hash,settings)
            VALUES ('sec_existing',1,'section','Section','section','private','active','doc_existing','','','{}')
            """
        )
        connection.execute(
            """
            INSERT INTO document_workbench_edges
                (id,parent_id,child_id,edge_kind,symbol,sort_order)
            VALUES ('ref_existing','doc_existing','sec_existing','section','section',0)
            """
        )

    database = JobDatabase(path)
    repository = database.document_workbench_repository

    existing = repository.require_reference(1, "ref_existing")
    assert existing["child_id"] == "sec_existing"
    assert existing["symbol"] == "section"

    with sqlite3.connect(path) as connection:
        sql = str(
            connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='document_workbench_edges'"
            ).fetchone()[0]
        ).casefold().replace(" ", "")
    assert "collatenocase" not in sql
    assert "unique(parent_id,child_id)" not in sql
    assert "unique(parent_id,symbol)" not in sql

    second = repository.create_resource(
        1,
        "section",
        name="Second",
        symbol="section",
        visibility="private",
        owner_id="doc_existing",
        content="",
        settings={"content_shape": "paragraphs"},
    )
    duplicate = repository.link(
        1,
        "doc_existing",
        second["id"],
        edge_kind="section",
        symbol="section",
        sort_order=1,
    )

    assert duplicate["id"] != "ref_existing"
    assert [edge["symbol"] for edge in repository.list_edges(1, "doc_existing")] == [
        "section",
        "section",
    ]
