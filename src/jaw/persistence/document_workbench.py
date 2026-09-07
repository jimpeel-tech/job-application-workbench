"""Persistence for the IDE-style JAW Document Workbench.

The Workbench keeps durable resources in SQLite and treats editor buffers as
separate recovery state. Documents and Templates may have display names; Sections
and Functions are presented by their symbols. Stable opaque JIDs and explicit graph
references carry identity and relationships.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable, Mapping
from typing import Any

ConnectionFactory = Callable[..., Any]

_RESOURCE_KINDS = {"document", "template", "section", "function"}
_VISIBILITIES = {"private", "global"}
_RESOURCE_STATES = {"active", "orphaned"}
_PREFIXES = {
    "document": "doc",
    "template": "tpl",
    "section": "sec",
    "function": "fn",
}

DOCUMENT_WORKBENCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS document_workbench_resources (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('document','template','section','function')),
    name TEXT NOT NULL DEFAULT '',
    symbol TEXT NOT NULL DEFAULT '',
    visibility TEXT NOT NULL DEFAULT 'private'
        CHECK(visibility IN ('private','global')),
    state TEXT NOT NULL DEFAULT 'active'
        CHECK(state IN ('active','orphaned')),
    owner_id TEXT REFERENCES document_workbench_resources(id) ON DELETE SET NULL,
    content TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    settings TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_workbench_documents (
    resource_id TEXT PRIMARY KEY
        REFERENCES document_workbench_resources(id) ON DELETE CASCADE,
    template_id TEXT NOT NULL
        REFERENCES document_workbench_resources(id),
    output_pattern TEXT NOT NULL DEFAULT 'Document.pdf'
);

CREATE TABLE IF NOT EXISTS document_workbench_edges (
    parent_id TEXT NOT NULL
        REFERENCES document_workbench_resources(id) ON DELETE CASCADE,
    child_id TEXT NOT NULL
        REFERENCES document_workbench_resources(id) ON DELETE CASCADE,
    edge_kind TEXT NOT NULL CHECK(edge_kind IN ('section','function')),
    symbol TEXT NOT NULL COLLATE NOCASE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(parent_id,child_id),
    UNIQUE(parent_id,symbol)
);

CREATE TABLE IF NOT EXISTS document_workbench_buffers (
    user_id INTEGER NOT NULL,
    resource_id TEXT NOT NULL
        REFERENCES document_workbench_resources(id) ON DELETE CASCADE,
    content TEXT NOT NULL DEFAULT '',
    base_hash TEXT NOT NULL DEFAULT '',
    cursor_start INTEGER NOT NULL DEFAULT 0,
    cursor_end INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id,resource_id)
);

CREATE INDEX IF NOT EXISTS idx_workbench_resources_user_kind
    ON document_workbench_resources(user_id,kind,visibility,state);
CREATE INDEX IF NOT EXISTS idx_workbench_resources_owner
    ON document_workbench_resources(owner_id,kind,state);
CREATE INDEX IF NOT EXISTS idx_workbench_documents_template
    ON document_workbench_documents(template_id);
CREATE INDEX IF NOT EXISTS idx_workbench_edges_parent
    ON document_workbench_edges(parent_id,sort_order);
CREATE INDEX IF NOT EXISTS idx_workbench_edges_child
    ON document_workbench_edges(child_id);
CREATE INDEX IF NOT EXISTS idx_workbench_buffers_user
    ON document_workbench_buffers(user_id,updated_at);
"""


class DocumentWorkbenchRepository:
    """SQLite boundary for Workbench resources, references, and recovery buffers."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connect = connection_factory
        self.initialize()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(DOCUMENT_WORKBENCH_SCHEMA)

    # Resources -----------------------------------------------------

    def create_resource(
        self,
        user_id: int,
        kind: str,
        *,
        name: str = "",
        symbol: str = "",
        visibility: str = "private",
        state: str = "active",
        owner_id: str | None = None,
        content: str = "",
        settings: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_kind = self._kind(kind)
        normalized_visibility = self._visibility(visibility)
        normalized_state = self._state(state)
        normalized_name = "" if normalized_kind in {"section", "function"} else str(name or "").strip()
        resource_id = self._new_id(normalized_kind)
        content_hash = _hash(content)
        with self._connect() as connection:
            if owner_id:
                self._require_owned(connection, user_id, owner_id)
            connection.execute(
                """
                INSERT INTO document_workbench_resources
                    (id,user_id,kind,name,symbol,visibility,state,owner_id,
                     content,content_hash,settings)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    resource_id,
                    user_id,
                    normalized_kind,
                    normalized_name,
                    str(symbol or "").strip(),
                    normalized_visibility,
                    normalized_state,
                    owner_id,
                    content,
                    content_hash,
                    _dump(settings),
                ),
            )
        created = self.get_resource(user_id, resource_id)
        assert created is not None
        return created

    def get_resource(self, user_id: int, resource_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM document_workbench_resources WHERE id=? AND user_id=?",
                (resource_id, user_id),
            ).fetchone()
        return _resource(row) if row else None

    def list_resources(
        self,
        user_id: int,
        *,
        kind: str | None = None,
        visibility: str | None = None,
        state: str | None = None,
        owner_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["user_id=?"]
        values: list[Any] = [user_id]
        if kind is not None:
            clauses.append("kind=?")
            values.append(self._kind(kind))
        if visibility is not None:
            clauses.append("visibility=?")
            values.append(self._visibility(visibility))
        if state is not None:
            clauses.append("state=?")
            values.append(self._state(state))
        if owner_id is not None:
            clauses.append("owner_id=?")
            values.append(owner_id)
        where = " AND ".join(clauses)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM document_workbench_resources
                WHERE {where}
                ORDER BY kind,name,created_at,id
                """,
                values,
            ).fetchall()
        return [_resource(row) for row in rows]

    def update_resource(
        self,
        user_id: int,
        resource_id: str,
        *,
        name: str | None = None,
        symbol: str | None = None,
        visibility: str | None = None,
        state: str | None = None,
        owner_id: str | None | object = ...,
        settings: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.require_resource(user_id, resource_id)
        if name is not None and current["kind"] in {"section", "function"}:
            raise ValueError("Sections and Functions are named by their symbol")
        next_name = current["name"] if name is None else str(name).strip()
        next_symbol = current["symbol"] if symbol is None else str(symbol).strip()
        next_visibility = (
            current["visibility"] if visibility is None else self._visibility(visibility)
        )
        next_state = current["state"] if state is None else self._state(state)
        next_owner = current.get("owner_id") if owner_id is ... else owner_id
        next_settings = current["settings"] if settings is None else dict(settings)
        with self._connect() as connection:
            if next_owner:
                self._require_owned(connection, user_id, str(next_owner))
            cursor = connection.execute(
                """
                UPDATE document_workbench_resources
                SET name=?, symbol=?, visibility=?, state=?, owner_id=?, settings=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND user_id=?
                """,
                (
                    next_name,
                    next_symbol,
                    next_visibility,
                    next_state,
                    next_owner,
                    _dump(next_settings),
                    resource_id,
                    user_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Workbench resource was not found")
        return self.require_resource(user_id, resource_id)

    def save_content(self, user_id: int, resource_id: str, content: str) -> dict[str, Any]:
        content_hash = _hash(content)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE document_workbench_resources
                SET content=?, content_hash=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND user_id=?
                """,
                (content, content_hash, resource_id, user_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Workbench resource was not found")
            connection.execute(
                "DELETE FROM document_workbench_buffers WHERE user_id=? AND resource_id=?",
                (user_id, resource_id),
            )
        return self.require_resource(user_id, resource_id)

    def delete_resource(self, user_id: int, resource_id: str) -> dict[str, Any]:
        current = self.require_resource(user_id, resource_id)
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM document_workbench_resources WHERE id=? AND user_id=?",
                (resource_id, user_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Workbench resource was not found")
        return current

    def require_resource(self, user_id: int, resource_id: str) -> dict[str, Any]:
        resource = self.get_resource(user_id, resource_id)
        if resource is None:
            raise ValueError("Workbench resource was not found")
        return resource

    # Documents -----------------------------------------------------

    def create_document(
        self,
        user_id: int,
        name: str,
        template_id: str,
        *,
        output_pattern: str,
    ) -> dict[str, Any]:
        template = self.require_resource(user_id, template_id)
        if template["kind"] != "template":
            raise ValueError("Document template must be a Template resource")
        document = self.create_resource(
            user_id,
            "document",
            name=name,
            visibility="private",
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO document_workbench_documents
                    (resource_id,template_id,output_pattern)
                VALUES (?,?,?)
                """,
                (document["id"], template_id, output_pattern),
            )
        created = self.get_document(user_id, document["id"])
        assert created is not None
        return created

    def get_document(self, user_id: int, document_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT r.*, d.template_id, d.output_pattern
                FROM document_workbench_resources r
                JOIN document_workbench_documents d ON d.resource_id=r.id
                WHERE r.id=? AND r.user_id=? AND r.kind='document'
                """,
                (document_id, user_id),
            ).fetchone()
        if row is None:
            return None
        value = _resource(row)
        value["template_id"] = str(row["template_id"])
        value["output_pattern"] = str(row["output_pattern"])
        return value

    def list_documents(self, user_id: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT r.*, d.template_id, d.output_pattern
                FROM document_workbench_resources r
                JOIN document_workbench_documents d ON d.resource_id=r.id
                WHERE r.user_id=? AND r.kind='document'
                ORDER BY r.created_at,r.id
                """,
                (user_id,),
            ).fetchall()
        values: list[dict[str, Any]] = []
        for row in rows:
            value = _resource(row)
            value["template_id"] = str(row["template_id"])
            value["output_pattern"] = str(row["output_pattern"])
            values.append(value)
        return values

    def documents_for_template(self, user_id: int, template_id: str) -> list[dict[str, Any]]:
        return [
            document
            for document in self.list_documents(user_id)
            if document["template_id"] == template_id
        ]

    def update_document(
        self,
        user_id: int,
        document_id: str,
        *,
        name: str | None = None,
        template_id: str | None = None,
        output_pattern: str | None = None,
    ) -> dict[str, Any]:
        current = self.get_document(user_id, document_id)
        if current is None:
            raise ValueError("Document was not found")
        if name is not None:
            self.update_resource(user_id, document_id, name=name)
        next_template = current["template_id"] if template_id is None else template_id
        template = self.require_resource(user_id, next_template)
        if template["kind"] != "template":
            raise ValueError("Document template must be a Template resource")
        next_output = current["output_pattern"] if output_pattern is None else str(output_pattern)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE document_workbench_documents
                SET template_id=?, output_pattern=?
                WHERE resource_id=?
                """,
                (next_template, next_output, document_id),
            )
        updated = self.get_document(user_id, document_id)
        assert updated is not None
        return updated

    # Edges ---------------------------------------------------------

    def list_edges(self, user_id: int, parent_id: str | None = None) -> list[dict[str, Any]]:
        clauses = ["p.user_id=?"]
        values: list[Any] = [user_id]
        if parent_id is not None:
            clauses.append("e.parent_id=?")
            values.append(parent_id)
        where = " AND ".join(clauses)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT e.*
                FROM document_workbench_edges e
                JOIN document_workbench_resources p ON p.id=e.parent_id
                WHERE {where}
                ORDER BY e.parent_id,e.sort_order,e.created_at,e.child_id
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def find_edge_symbol(
        self,
        user_id: int,
        parent_id: str,
        symbol: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT e.*
                FROM document_workbench_edges e
                JOIN document_workbench_resources p ON p.id=e.parent_id
                WHERE p.user_id=? AND e.parent_id=? AND e.symbol=? COLLATE NOCASE
                """,
                (user_id, parent_id, symbol),
            ).fetchone()
        return dict(row) if row else None

    def link(
        self,
        user_id: int,
        parent_id: str,
        child_id: str,
        *,
        edge_kind: str,
        symbol: str,
        sort_order: int | None = None,
    ) -> dict[str, Any]:
        parent = self.require_resource(user_id, parent_id)
        child = self.require_resource(user_id, child_id)
        normalized_edge = str(edge_kind).strip().casefold()
        expected = {"section": "section", "function": "function"}.get(normalized_edge)
        if expected is None:
            raise ValueError("Workbench edge must be section or function")
        if child["kind"] != expected:
            raise ValueError(f"A {normalized_edge} edge requires a {expected} resource")
        if normalized_edge == "section" and parent["kind"] != "document":
            raise ValueError("Sections are linked in Document scope")
        if normalized_edge == "function" and parent["kind"] != "section":
            raise ValueError("Functions are linked in Section scope")
        clean_symbol = str(symbol or "").strip()
        if not clean_symbol:
            raise ValueError("Workbench edge symbol is required")
        with self._connect() as connection:
            if sort_order is None:
                row = connection.execute(
                    """
                    SELECT COALESCE(MAX(sort_order),-1)+1 AS next_order
                    FROM document_workbench_edges WHERE parent_id=?
                    """,
                    (parent_id,),
                ).fetchone()
                sort_order = int(row["next_order"])
            connection.execute(
                """
                INSERT INTO document_workbench_edges
                    (parent_id,child_id,edge_kind,symbol,sort_order)
                VALUES (?,?,?,?,?)
                ON CONFLICT(parent_id,child_id) DO UPDATE SET
                    edge_kind=excluded.edge_kind,
                    symbol=excluded.symbol,
                    sort_order=excluded.sort_order
                """,
                (parent_id, child_id, normalized_edge, clean_symbol, sort_order),
            )
        edge = self.find_edge_symbol(user_id, parent_id, clean_symbol)
        if edge is None:
            raise ValueError("Workbench edge could not be created")
        return edge

    def unlink(self, user_id: int, parent_id: str, child_id: str) -> dict[str, Any] | None:
        self.require_resource(user_id, parent_id)
        self.require_resource(user_id, child_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM document_workbench_edges
                WHERE parent_id=? AND child_id=?
                """,
                (parent_id, child_id),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "DELETE FROM document_workbench_edges WHERE parent_id=? AND child_id=?",
                (parent_id, child_id),
            )
        return dict(row)

    # Recovery buffers ---------------------------------------------

    def checkpoint_buffer(
        self,
        user_id: int,
        resource_id: str,
        content: str,
        *,
        cursor_start: int = 0,
        cursor_end: int = 0,
    ) -> dict[str, Any]:
        resource = self.require_resource(user_id, resource_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO document_workbench_buffers
                    (user_id,resource_id,content,base_hash,cursor_start,cursor_end,updated_at)
                VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(user_id,resource_id) DO UPDATE SET
                    content=excluded.content,
                    base_hash=excluded.base_hash,
                    cursor_start=excluded.cursor_start,
                    cursor_end=excluded.cursor_end,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    resource_id,
                    content,
                    resource["content_hash"],
                    max(0, int(cursor_start)),
                    max(0, int(cursor_end)),
                ),
            )
        return self.get_buffer(user_id, resource_id) or {}

    def get_buffer(self, user_id: int, resource_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM document_workbench_buffers
                WHERE user_id=? AND resource_id=?
                """,
                (user_id, resource_id),
            ).fetchone()
        return dict(row) if row else None

    def list_buffers(self, user_id: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM document_workbench_buffers
                WHERE user_id=? ORDER BY updated_at,resource_id
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_buffer(self, user_id: int, resource_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM document_workbench_buffers WHERE user_id=? AND resource_id=?",
                (user_id, resource_id),
            )

    # Helpers -------------------------------------------------------

    @staticmethod
    def _new_id(kind: str) -> str:
        return f"{_PREFIXES[kind]}_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _kind(value: str) -> str:
        kind = str(value or "").strip().casefold()
        if kind not in _RESOURCE_KINDS:
            raise ValueError("Workbench resource kind is invalid")
        return kind

    @staticmethod
    def _visibility(value: str) -> str:
        visibility = str(value or "").strip().casefold()
        if visibility not in _VISIBILITIES:
            raise ValueError("Workbench visibility must be private or global")
        return visibility

    @staticmethod
    def _state(value: str) -> str:
        state = str(value or "").strip().casefold()
        if state not in _RESOURCE_STATES:
            raise ValueError("Workbench resource state must be active or orphaned")
        return state

    @staticmethod
    def _require_owned(connection: sqlite3.Connection, user_id: int, resource_id: str) -> None:
        row = connection.execute(
            "SELECT 1 FROM document_workbench_resources WHERE id=? AND user_id=?",
            (resource_id, user_id),
        ).fetchone()
        if row is None:
            raise ValueError("Workbench owner resource was not found")


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _dump(value: Mapping[str, Any] | None) -> str:
    return json.dumps(dict(value or {}), ensure_ascii=False, sort_keys=True)


def _load(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _resource(row: sqlite3.Row) -> dict[str, Any]:
    value = {key: row[key] for key in row.keys() if key in {
        "id", "user_id", "kind", "name", "symbol", "visibility", "state",
        "owner_id", "content", "content_hash", "settings", "created_at", "updated_at",
    }}
    value["settings"] = _load(row["settings"])
    return value


__all__ = ["DOCUMENT_WORKBENCH_SCHEMA", "DocumentWorkbenchRepository"]
