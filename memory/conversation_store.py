"""Local SQLite storage for SKYFALL conversations.

This module stores the application's conversation index and visible transcript.
Copilot SDK session state is separately persisted by the Copilot runtime and is
resumed by its session ID. No credentials or access tokens belong in this DB.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

LATEST_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class ConversationRecord:
    id: str
    title: str
    copilot_session_id: str
    created_at: str
    updated_at: str
    message_count: int
    sdk_session_initialized: bool


@dataclass(frozen=True)
class MessageRecord:
    id: int
    conversation_id: str
    role: str
    content: str
    status: str
    created_at: str


class ConversationStore:
    """Thread-safe, small local conversation database backed by SQLite."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        if database_path is None:
            local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home()))
            database_path = local_app_data / "SKYFALL" / "data" / "skyfall.db"

        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="microseconds")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.database_path,
            timeout=20,
            isolation_level="DEFERRED",
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 20000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
            )
            row = connection.execute(
                "SELECT version FROM schema_version LIMIT 1"
            ).fetchone()
            if row is None:
                connection.execute("INSERT INTO schema_version (version) VALUES (0)")
            self._migrate(connection)

    def _migrate(self, connection: sqlite3.Connection) -> None:
        current = int(
            connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()["version"]
        )
        migrations = {
            1: self._migration_001_base_schema,
            2: self._migration_002_backup_log,
        }
        for version in range(current + 1, LATEST_SCHEMA_VERSION + 1):
            migration = migrations.get(version)
            if migration is None:
                raise RuntimeError(f"Missing migration for schema version {version}")
            migration(connection)
            connection.execute("UPDATE schema_version SET version = ?", (version,))

    @staticmethod
    def _migration_001_base_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                copilot_session_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                sdk_session_initialized INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'complete',
                created_at TEXT NOT NULL,
                FOREIGN KEY(conversation_id)
                    REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_id "
            "ON messages(conversation_id, id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_updated_at "
            "ON conversations(updated_at DESC)"
        )

    @staticmethod
    def _migration_002_backup_log(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS backup_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_path TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'database',
                created_at TEXT NOT NULL
            )
            """
        )

    @staticmethod
    def _to_conversation(row: sqlite3.Row) -> ConversationRecord:
        return ConversationRecord(
            id=row["id"],
            title=row["title"],
            copilot_session_id=row["copilot_session_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            message_count=int(row["message_count"]),
            sdk_session_initialized=bool(row["sdk_session_initialized"]),
        )

    def create_conversation(self, title: str = "New conversation") -> ConversationRecord:
        conversation_id = str(uuid.uuid4())
        copilot_session_id = f"skyfall-{uuid.uuid4().hex}"
        now = self._now()
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO conversations
                    (id, title, copilot_session_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversation_id, title.strip() or "New conversation", copilot_session_id, now, now),
            )
        return self.get_conversation(conversation_id)  # type: ignore[return-value]

    def get_or_create_active_conversation(self) -> ConversationRecord:
        active_id = self.get_active_conversation_id()
        if active_id:
            existing = self.get_conversation(active_id)
            if existing is not None:
                return existing
        conversations = self.list_conversations(limit=1)
        if conversations:
            conversation = conversations[0]
        else:
            conversation = self.create_conversation()
        self.set_active_conversation(conversation.id)
        return conversation

    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                """
                SELECT c.id, c.title, c.copilot_session_id, c.created_at,
                       c.updated_at, c.sdk_session_initialized,
                       COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.id = ?
                GROUP BY c.id
                """,
                (conversation_id,),
            ).fetchone()
        return self._to_conversation(row) if row else None

    def list_conversations(self, limit: int = 100) -> list[ConversationRecord]:
        safe_limit = max(1, min(int(limit), 500))
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """
                SELECT c.id, c.title, c.copilot_session_id, c.created_at,
                       c.updated_at, c.sdk_session_initialized,
                       COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                GROUP BY c.id
                HAVING COUNT(m.id) > 0
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [self._to_conversation(row) for row in rows]

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        status: str = "complete",
    ) -> int:
        clean_role = role.strip().lower()
        if clean_role not in {"user", "assistant", "system"}:
            raise ValueError(f"Unsupported message role: {role}")
        if not isinstance(content, str):
            raise TypeError("Message content must be a string.")

        now = self._now()
        with self._lock, self._connection() as connection:
            exists = connection.execute(
                "SELECT title FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if exists is None:
                raise KeyError(f"Conversation not found: {conversation_id}")

            cursor = connection.execute(
                """
                INSERT INTO messages
                    (conversation_id, role, content, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversation_id, clean_role, content, status, now),
            )

            title = exists["title"]
            if clean_role == "user" and title == "New conversation":
                candidate = " ".join(content.split())
                if candidate:
                    title = candidate[:52] + ("…" if len(candidate) > 52 else "")

            connection.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, now, conversation_id),
            )
            connection.execute(
                "INSERT INTO app_state(key, value) VALUES('active_conversation_id', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (conversation_id,),
            )
            return int(cursor.lastrowid)

    def get_messages(self, conversation_id: str) -> list[MessageRecord]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, conversation_id, role, content, status, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [
            MessageRecord(
                id=int(row["id"]),
                conversation_id=row["conversation_id"],
                role=row["role"],
                content=row["content"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def set_sdk_session_initialized(self, conversation_id: str, initialized: bool = True) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE conversations SET sdk_session_initialized = ?, updated_at = ? WHERE id = ?",
                (1 if initialized else 0, self._now(), conversation_id),
            )

    def set_active_conversation(self, conversation_id: str) -> None:
        with self._lock, self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if exists is None:
                raise KeyError(f"Conversation not found: {conversation_id}")
            connection.execute(
                "INSERT INTO app_state(key, value) VALUES('active_conversation_id', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (conversation_id,),
            )

    def get_active_conversation_id(self) -> str | None:
        return self.get_state("active_conversation_id")

    def set_state(self, key: str, value: object) -> None:
        """Persist a named application state value in app_state."""
        clean_key = str(key).strip()
        if not clean_key:
            raise ValueError("State key must be a non-empty string.")
        if value is None:
            raise ValueError("State value must not be None; use delete_state to remove a key.")
        text_value = value if isinstance(value, str) else str(value)
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO app_state(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (clean_key, text_value),
            )

    def get_state(self, key: str, default: object = None) -> str | None:
        """Return the value stored for key, or default when absent."""
        clean_key = str(key).strip()
        if not clean_key:
            return default  # type: ignore[return-value]
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM app_state WHERE key = ?", (clean_key,)
            ).fetchone()
        if row is None:
            return default  # type: ignore[return-value]
        return row["value"]

    def delete_state(self, key: str) -> None:
        """Remove a named application state value."""
        clean_key = str(key).strip()
        if not clean_key:
            return
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM app_state WHERE key = ?", (clean_key,))

    def list_state_keys(self) -> list[str]:
        """Return all persisted application state keys in sorted order."""
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT key FROM app_state ORDER BY key ASC"
            ).fetchall()
        return [str(row["key"]) for row in rows]

    def get_schema_version(self) -> int:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        return int(row["version"]) if row else 0

    def backup_database(self, destination_path: str | Path) -> Path:
        destination = Path(destination_path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Remove any stale destination/WAL artifacts so backup is clean.
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(str(destination) + suffix)
            if candidate.exists():
                candidate.unlink()

        with self._lock:
            source = sqlite3.connect(self.database_path, timeout=20)
            try:
                source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                target = sqlite3.connect(destination, timeout=20)
                try:
                    source.backup(target)
                    target.commit()
                finally:
                    target.close()
            finally:
                source.close()

        self._record_backup(destination, "database")
        return destination

    def _record_backup(self, destination: Path, kind: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO backup_log (backup_path, kind, created_at) VALUES (?, ?, ?)",
                (str(destination), kind, self._now()),
            )

    def export_conversations_json(self, path: str | Path) -> Path:
        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)

        with self._lock, self._connection() as connection:
            conversation_rows = connection.execute(
                """
                SELECT id, title, copilot_session_id, created_at, updated_at,
                       sdk_session_initialized
                FROM conversations
                ORDER BY created_at ASC
                """
            ).fetchall()

            conversations = []
            for row in conversation_rows:
                message_rows = connection.execute(
                    """
                    SELECT id, role, content, status, created_at
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id ASC
                    """,
                    (row["id"],),
                ).fetchall()
                conversations.append(
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "copilot_session_id": row["copilot_session_id"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "sdk_session_initialized": bool(row["sdk_session_initialized"]),
                        "messages": [
                            {
                                "id": int(m["id"]),
                                "role": m["role"],
                                "content": m["content"],
                                "status": m["status"],
                                "created_at": m["created_at"],
                            }
                            for m in message_rows
                        ],
                    }
                )

            active_id = connection.execute(
                "SELECT value FROM app_state WHERE key = 'active_conversation_id'"
            ).fetchone()
            active_value = active_id["value"] if active_id else None

            payload = {
                "schema_version": self.get_schema_version(),
                "exported_at": self._now(),
                "active_conversation_id": active_value,
                "conversations": conversations,
            }

        with destination.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return destination

    def import_conversations_json(
        self, path: str | Path, on_conflict: str = "skip"
    ) -> dict[str, int]:
        if on_conflict not in {"skip", "overwrite", "rename"}:
            raise ValueError(f"Unsupported conflict strategy: {on_conflict}")

        source = Path(path).expanduser().resolve()
        with source.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        conversations = payload.get("conversations", [])
        imported = 0
        skipped = 0
        active_id = payload.get("active_conversation_id")
        active_mapped = None

        for item in conversations:
            conversation_id = str(item["id"])
            with self._lock, self._connection() as connection:
                existing = connection.execute(
                    "SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)
                ).fetchone()

                if existing is not None and on_conflict == "skip":
                    skipped += 1
                    continue

                target_id = conversation_id
                if existing is not None and on_conflict == "rename":
                    target_id = str(uuid.uuid4())

                title = item.get("title", "New conversation")
                created_at = item.get("created_at", self._now())
                updated_at = item.get("updated_at", self._now())
                sdk_init = 1 if item.get("sdk_session_initialized") else 0

                if existing is not None and on_conflict == "overwrite":
                    connection.execute(
                        "DELETE FROM messages WHERE conversation_id = ?",
                        (conversation_id,),
                    )
                    connection.execute(
                        """
                        UPDATE conversations
                        SET title = ?, copilot_session_id = ?, created_at = ?,
                            updated_at = ?, sdk_session_initialized = ?
                        WHERE id = ?
                        """,
                        (
                            title,
                            item.get("copilot_session_id", f"skyfall-{uuid.uuid4().hex}"),
                            created_at,
                            updated_at,
                            sdk_init,
                            conversation_id,
                        ),
                    )
                elif existing is None or on_conflict == "rename":
                    copilot_session_id = item.get("copilot_session_id")
                    if on_conflict == "rename" or not copilot_session_id:
                        copilot_session_id = f"skyfall-{uuid.uuid4().hex}"
                    connection.execute(
                        """
                        INSERT INTO conversations
                            (id, title, copilot_session_id, created_at, updated_at,
                             sdk_session_initialized)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (target_id, title, copilot_session_id, created_at, updated_at, sdk_init),
                    )

                for message in item.get("messages", []):
                    role = str(message.get("role", "user")).strip().lower()
                    if role not in {"user", "assistant", "system"}:
                        role = "system"
                    connection.execute(
                        """
                        INSERT INTO messages
                            (conversation_id, role, content, status, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            target_id,
                            role,
                            str(message.get("content", "")),
                            str(message.get("status", "complete")),
                            message.get("created_at", self._now()),
                        ),
                    )

                imported += 1
                if active_id == conversation_id:
                    active_mapped = target_id

        if active_mapped is not None:
            try:
                self.set_active_conversation(active_mapped)
            except KeyError:
                pass

        return {"imported": imported, "skipped": skipped}

    def delete_conversation(self, conversation_id: str) -> None:
        """Delete the local index and messages; SDK transcript deletion is separate."""
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            active = connection.execute(
                "SELECT value FROM app_state WHERE key = 'active_conversation_id'"
            ).fetchone()
            if active and active["value"] == conversation_id:
                connection.execute(
                    "DELETE FROM app_state WHERE key = 'active_conversation_id'"
                )
