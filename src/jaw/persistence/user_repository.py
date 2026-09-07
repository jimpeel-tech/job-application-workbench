from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..paths import DATABASE_SCHEMA_VERSION

USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class UserAccountRecord:
    id: int
    name: str
    data: dict[str, Any]


@dataclass(frozen=True)
class UserSummary:
    id: int
    name: str


class UserRepositorySession:
    """Account and preference operations inside one SQLite transaction."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize_schema(self) -> None:
        self._connection.executescript(USER_SCHEMA)
        self._connection.execute(
            f"PRAGMA user_version = {DATABASE_SCHEMA_VERSION}"
        )

    def count_users(self) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) FROM user_accounts"
        ).fetchone()
        return int(row[0])

    def get_preference(self, key: str) -> str | None:
        row = self._connection.execute(
            "SELECT value FROM user_preferences WHERE key=?",
            (key,),
        ).fetchone()
        return str(row[0]) if row is not None else None

    def set_preference(self, key: str, value: str) -> None:
        self._connection.execute(
            """
            INSERT OR REPLACE INTO user_preferences(key,value)
            VALUES (?,?)
            """,
            (key, value),
        )

    def active_user_id(self) -> int:
        value = self.get_preference("active_user_id")
        if value is not None:
            return int(value)

        first = self.first_user()
        if first is None:
            raise ValueError("No users exist")
        return first.id

    def get_user(self, user_id: int) -> UserAccountRecord | None:
        row = self._connection.execute(
            """
            SELECT id,name,data_json
            FROM user_accounts
            WHERE id=?
            """,
            (user_id,),
        ).fetchone()
        return self._account(row)

    def first_user(self) -> UserAccountRecord | None:
        row = self._connection.execute(
            """
            SELECT id,name,data_json
            FROM user_accounts
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
        return self._account(row)

    def list_users(self) -> list[UserSummary]:
        return [
            UserSummary(id=int(row["id"]), name=str(row["name"]))
            for row in self._connection.execute(
                """
                SELECT id,name
                FROM user_accounts
                ORDER BY name COLLATE NOCASE
                """
            )
        ]

    def create_user(self, name: str, data: dict[str, Any]) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO user_accounts(name,data_json)
            VALUES (?,?)
            """,
            (name, self._encode(data)),
        )
        return int(cursor.lastrowid)

    def update_user(self, user_id: int, data: dict[str, Any]) -> None:
        self._connection.execute(
            """
            UPDATE user_accounts
            SET data_json=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (self._encode(data), user_id),
        )

    def user_exists(self, user_id: int) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM user_accounts WHERE id=?",
                (user_id,),
            ).fetchone()
            is not None
        )

    def delete_user(self, user_id: int) -> None:
        self._connection.execute(
            "DELETE FROM user_accounts WHERE id=?",
            (user_id,),
        )

    @staticmethod
    def _encode(data: dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _account(row: sqlite3.Row | None) -> UserAccountRecord | None:
        if row is None:
            return None
        return UserAccountRecord(
            id=int(row["id"]),
            name=str(row["name"]),
            data=json.loads(row["data_json"]),
        )


class UserRepository:
    """SQLite boundary for user accounts and global user preferences."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @contextmanager
    def transaction(self) -> Iterator[UserRepositorySession]:
        with self._lock:
            connection = sqlite3.connect(self.path, timeout=10)
            connection.row_factory = sqlite3.Row
            try:
                yield UserRepositorySession(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()
