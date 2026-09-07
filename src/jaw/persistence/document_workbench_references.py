"""Reference-aware persistence for the JAW Document Workbench graph.

Resources have stable opaque JIDs. Every durable graph reference has its own
stable ``ref_*`` JID as well. Reference identity is independent from the visible
Jinja symbol, so one parent may contain duplicate symbols. A Global resource may
be referenced more than once; a private Section or Function JID has one durable
reference at a time.
"""

from __future__ import annotations

import uuid
from typing import Any

from .document_workbench import (
    DOCUMENT_WORKBENCH_SCHEMA as _BASE_SCHEMA,
)
from .document_workbench import (
    DocumentWorkbenchRepository as _BaseDocumentWorkbenchRepository,
)

_LEGACY_EDGE_SCHEMA = """CREATE TABLE IF NOT EXISTS document_workbench_edges (
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
);"""

_REFERENCE_EDGE_SCHEMA = """CREATE TABLE IF NOT EXISTS document_workbench_edges (
    id TEXT PRIMARY KEY,
    parent_id TEXT NOT NULL
        REFERENCES document_workbench_resources(id) ON DELETE CASCADE,
    child_id TEXT NOT NULL
        REFERENCES document_workbench_resources(id) ON DELETE CASCADE,
    edge_kind TEXT NOT NULL CHECK(edge_kind IN ('section','function')),
    symbol TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);"""

if _LEGACY_EDGE_SCHEMA not in _BASE_SCHEMA:
    raise RuntimeError("Workbench edge schema changed unexpectedly")

DOCUMENT_WORKBENCH_SCHEMA = _BASE_SCHEMA.replace(
    _LEGACY_EDGE_SCHEMA,
    _REFERENCE_EDGE_SCHEMA,
    1,
)


class DocumentWorkbenchRepository(_BaseDocumentWorkbenchRepository):
    """Workbench repository with first-class, case-sensitive reference JIDs."""

    def initialize(self) -> None:
        with self._connect() as connection:
            table = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='document_workbench_edges'"
            ).fetchone()
            table_sql = str(table["sql"] or "") if table else ""
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(document_workbench_edges)")
            }
            incompatible = bool(columns) and (
                "id" not in columns
                or "collate nocase" in table_sql.casefold()
                or "unique(parent_id,child_id)" in table_sql.replace(" ", "").casefold()
                or "unique(parent_id,symbol)" in table_sql.replace(" ", "").casefold()
                or "primarykey(parent_id,child_id)" in table_sql.replace(" ", "").casefold()
            )

            rows: list[dict[str, Any]] = []
            if incompatible:
                select_id = "id," if "id" in columns else "NULL AS id,"
                rows = [
                    dict(row)
                    for row in connection.execute(
                        f"""
                        SELECT {select_id} parent_id,child_id,edge_kind,symbol,
                               sort_order,created_at
                        FROM document_workbench_edges
                        ORDER BY parent_id,sort_order,created_at,child_id
                        """
                    ).fetchall()
                ]
                connection.execute("DROP TABLE document_workbench_edges")

            connection.executescript(DOCUMENT_WORKBENCH_SCHEMA)

            # Sections and Functions have no independent display-name concept.
            # Existing dev data is normalized in place; the visible symbol is the
            # only human-facing label while the resource JID remains identity.
            connection.execute(
                """
                UPDATE document_workbench_resources
                SET name=''
                WHERE kind IN ('section','function') AND name<>''
                """
            )

            for row in rows:
                connection.execute(
                    """
                    INSERT INTO document_workbench_edges
                        (id,parent_id,child_id,edge_kind,symbol,sort_order,created_at)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        str(row.get("id") or self._new_reference_jid()),
                        row["parent_id"],
                        row["child_id"],
                        row["edge_kind"],
                        row["symbol"],
                        int(row["sort_order"]),
                        row["created_at"],
                    ),
                )

    def get_reference(
        self,
        user_id: int,
        reference_id: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT e.*
                FROM document_workbench_edges e
                JOIN document_workbench_resources p ON p.id=e.parent_id
                WHERE p.user_id=? AND e.id=?
                """,
                (user_id, reference_id),
            ).fetchone()
        return dict(row) if row else None

    def require_reference(self, user_id: int, reference_id: str) -> dict[str, Any]:
        reference = self.get_reference(user_id, reference_id)
        if reference is None:
            raise ValueError("Workbench reference was not found")
        return reference

    def find_edges_symbol(
        self,
        user_id: int,
        parent_id: str,
        symbol: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT e.*
                FROM document_workbench_edges e
                JOIN document_workbench_resources p ON p.id=e.parent_id
                WHERE p.user_id=? AND e.parent_id=? AND e.symbol=?
                ORDER BY e.sort_order,e.created_at,e.id
                """,
                (user_id, parent_id, str(symbol)),
            ).fetchall()
        return [dict(row) for row in rows]

    def find_edge_symbol(
        self,
        user_id: int,
        parent_id: str,
        symbol: str,
    ) -> dict[str, Any] | None:
        values = self.find_edges_symbol(user_id, parent_id, symbol)
        return values[0] if values else None

    def link(
        self,
        user_id: int,
        parent_id: str,
        child_id: str,
        *,
        edge_kind: str,
        symbol: str,
        sort_order: int | None = None,
        reference_id: str | None = None,
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

        # Duplicate visible symbols are independent references. Reusing the same
        # resource JID, however, is an explicit Global-resource operation. Private
        # resources keep a single owner/reference; stage -> reuse works because a
        # staged resource has no inbound reference before it is linked again.
        if not reference_id and child["visibility"] != "global":
            inbound = [
                edge
                for edge in self.list_edges(user_id)
                if edge["child_id"] == child_id
            ]
            if inbound:
                raise ValueError(
                    "Private Sections and Functions can only be referenced once; "
                    "make the resource Global before reusing it"
                )

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

            if reference_id:
                current = self.require_reference(user_id, reference_id)
                if current["parent_id"] != parent_id or current["child_id"] != child_id:
                    raise ValueError("Reference JID does not match the selected relationship")
                connection.execute(
                    """
                    UPDATE document_workbench_edges
                    SET edge_kind=?,symbol=?,sort_order=?
                    WHERE id=?
                    """,
                    (normalized_edge, clean_symbol, int(sort_order), reference_id),
                )
                created_id = reference_id
            else:
                created_id = self._new_reference_jid()
                connection.execute(
                    """
                    INSERT INTO document_workbench_edges
                        (id,parent_id,child_id,edge_kind,symbol,sort_order)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (
                        created_id,
                        parent_id,
                        child_id,
                        normalized_edge,
                        clean_symbol,
                        int(sort_order),
                    ),
                )

        return self.require_reference(user_id, created_id)

    def unlink_reference(
        self,
        user_id: int,
        reference_id: str,
    ) -> dict[str, Any] | None:
        reference = self.get_reference(user_id, reference_id)
        if reference is None:
            return None
        with self._connect() as connection:
            connection.execute("DELETE FROM document_workbench_edges WHERE id=?", (reference_id,))
        return reference

    def unlink(
        self,
        user_id: int,
        parent_id: str,
        child_id: str,
    ) -> dict[str, Any] | None:
        self.require_resource(user_id, parent_id)
        self.require_resource(user_id, child_id)
        matches = [
            edge
            for edge in self.list_edges(user_id, parent_id)
            if edge["child_id"] == child_id
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError("reference_id is required when a resource is referenced more than once")
        return self.unlink_reference(user_id, str(matches[0]["id"]))

    @staticmethod
    def _new_reference_jid() -> str:
        return f"ref_{uuid.uuid4().hex[:16]}"


__all__ = ["DOCUMENT_WORKBENCH_SCHEMA", "DocumentWorkbenchRepository"]
