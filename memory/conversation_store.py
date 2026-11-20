"""Local SQLite storage for SKYFALL conversations.

This module stores the application's conversation index and visible transcript.
Copilot SDK session state is separately persisted by the Copilot runtime and is
resumed by its session ID. No credentials or access tokens belong in this DB.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


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
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM app_state WHERE key = 'active_conversation_id'"
            ).fetchone()
        return row["value"] if row else None

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
    def update_conversation_title(self, conversation_id: str, title: str) -> None:
        clean_title = (title or "").strip() or "New conversation"
        with self._lock, self._connection() as connection:
            exists = connection.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if exists is None:
                raise KeyError(f"Conversation not found: {conversation_id}")
            connection.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (clean_title, self._now(), conversation_id))

    def delete_message(self, message_id: int) -> None:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT conversation_id FROM messages WHERE id = ?", (message_id,)).fetchone()
            if row is None:
                raise KeyError(f"Message not found: {message_id}")
            conversation_id = row["conversation_id"]
            connection.execute("DELETE FROM messages WHERE id = ?", (message_id,))
            connection.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (self._now(), conversation_id))

    def search_conversations(self, query: str, limit: int = 50) -> list[ConversationRecord]:
        needle = (query or "").strip()
        if not needle:
            return self.list_conversations(limit=limit)
        safe_limit = max(1, min(int(limit), 500))
        like = f"%{needle}%"
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT c.id, c.title, c.copilot_session_id, c.created_at, "
                "c.updated_at, c.sdk_session_initialized, "
                "(SELECT COUNT(*) FROM messages m2 WHERE m2.conversation_id = c.id) AS message_count "
                "FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id "
                "WHERE c.title LIKE ? COLLATE NOCASE OR m.content LIKE ? COLLATE NOCASE "
                "ORDER BY c.updated_at DESC LIMIT ?",
                (like, like, safe_limit),
            ).fetchall()
        return [self._to_conversation(row) for row in rows]

    def export_conversation_markdown(self, conversation_id: str) -> str:
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            raise KeyError(f"Conversation not found: {conversation_id}")
        messages = self.get_messages(conversation_id)
        lines = [f"# {conversation.title}", "", f"- ID: `{conversation.id}`",
                 f"- Copilot Session ID: `{conversation.copilot_session_id}`",
                 f"- SDK Session Initialized: {conversation.sdk_session_initialized}",
                 f"- Created: {conversation.created_at}", f"- Updated: {conversation.updated_at}",
                 f"- Messages: {conversation.message_count}", "", "---", ""]
        for message in messages:
            lines.append(f"## {message.role.capitalize()} - {message.created_at} (status: {message.status})")
            lines.append("")
            lines.append(message.content)
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def backup_database(self, destination):
        from pathlib import Path as _Path
        destination_path = _Path(destination).expanduser().resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            source = sqlite3.connect(self.database_path)
            try:
                target = sqlite3.connect(destination_path)
                try:
                    source.backup(target)
                finally:
                    target.close()
            finally:
                source.close()
        return destination_path
