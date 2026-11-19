"""Backup and export utilities for the Data_Memory SQLite store.

This module operates on a copy of `Data_Memory/skyfall_memory.sqlite3` and never
modifies the source database. It mirrors the conventions used in
`memory/conversation_store.py`.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(database_path), timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 20000")
    return connection


def backup_data_memory(source_path: str | Path, destination_path: str | Path) -> Path:
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = Path(str(destination) + suffix)
        if candidate.exists():
            candidate.unlink()

    connection = sqlite3.connect(str(source), timeout=20)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        target = sqlite3.connect(str(destination), timeout=20)
        try:
            connection.backup(target)
            target.commit()
        finally:
            target.close()
    finally:
        connection.close()

    return destination


def export_data_memory_json(source_path: str | Path, destination_path: str | Path) -> Path:
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    connection = _connect(source)
    try:
        def rows(table: str) -> list[dict[str, Any]]:
            try:
                cursor = connection.execute(f"SELECT * FROM {table}")
            except sqlite3.OperationalError:
                return []
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

        payload = {
            "conversations": rows("conversations"),
            "messages": rows("messages"),
            "memory_documents": rows("memory_documents"),
            "assets": rows("assets"),
            "metadata": rows("metadata"),
        }
    finally:
        connection.close()

    with destination.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
    return destination


def import_data_memory_json(
    source_path: str | Path,
    destination_path: str | Path,
    on_conflict: str = "skip",
) -> dict[str, int]:
    if on_conflict not in {"skip", "overwrite"}:
        raise ValueError(f"Unsupported conflict strategy: {on_conflict}")

    src = Path(source_path).expanduser().resolve()
    dst = Path(destination_path).expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    with src.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    # Ensure destination exists; if not, seed it from source (schema + data) via backup.
    if not dst.exists():
        backup_data_memory(src, dst)

    connection = _connect(dst)
    try:
        imported = {"conversations": 0, "messages": 0, "memory_documents": 0, "assets": 0, "metadata": 0}
        skipped = {"conversations": 0, "messages": 0, "memory_documents": 0, "assets": 0, "metadata": 0}

        # conversations
        for item in payload.get("conversations", []):
            cid = item["conversation_id"]
            existing = connection.execute(
                "SELECT 1 FROM conversations WHERE conversation_id = ?", (cid,)
            ).fetchone()
            if existing is not None and on_conflict == "skip":
                skipped["conversations"] += 1
                continue
            if existing is not None and on_conflict == "overwrite":
                connection.execute("DELETE FROM conversations WHERE conversation_id = ?", (cid,))
            columns = list(item.keys())
            placeholders = ", ".join("?" for _ in columns)
            col_sql = ", ".join(columns)
            connection.execute(
                f"INSERT INTO conversations ({col_sql}) VALUES ({placeholders})",
                [item[c] for c in columns],
            )
            imported["conversations"] += 1

        # messages
        for item in payload.get("messages", []):
            mid = item.get("message_id")
            existing = None
            if mid is not None:
                existing = connection.execute(
                    "SELECT 1 FROM messages WHERE message_id = ?", (mid,)
                ).fetchone()
            if existing is not None and on_conflict == "skip":
                skipped["messages"] += 1
                continue
            if existing is not None and on_conflict == "overwrite" and mid is not None:
                connection.execute("DELETE FROM messages WHERE message_id = ?", (mid,))
            columns = list(item.keys())
            placeholders = ", ".join("?" for _ in columns)
            col_sql = ", ".join(columns)
            connection.execute(
                f"INSERT INTO messages ({col_sql}) VALUES ({placeholders})",
                [item[c] for c in columns],
            )
            imported["messages"] += 1

        # memory_documents (unique path)
        for item in payload.get("memory_documents", []):
            path = item["path"]
            existing = connection.execute(
                "SELECT 1 FROM memory_documents WHERE path = ?", (path,)
            ).fetchone()
            if existing is not None and on_conflict == "skip":
                skipped["memory_documents"] += 1
                continue
            if existing is not None and on_conflict == "overwrite":
                connection.execute("DELETE FROM memory_documents WHERE path = ?", (path,))
            columns = list(item.keys())
            # drop autoincrement document_id to let DB assign
            if "document_id" in columns:
                columns = [c for c in columns if c != "document_id"]
            placeholders = ", ".join("?" for _ in columns)
            col_sql = ", ".join(columns)
            connection.execute(
                f"INSERT INTO memory_documents ({col_sql}) VALUES ({placeholders})",
                [item[c] for c in columns],
            )
            imported["memory_documents"] += 1

        # assets (unique relative_path)
        for item in payload.get("assets", []):
            rp = item["relative_path"]
            existing = connection.execute(
                "SELECT 1 FROM assets WHERE relative_path = ?", (rp,)
            ).fetchone()
            if existing is not None and on_conflict == "skip":
                skipped["assets"] += 1
                continue
            if existing is not None and on_conflict == "overwrite":
                connection.execute("DELETE FROM assets WHERE relative_path = ?", (rp,))
            columns = list(item.keys())
            if "asset_id" in columns:
                columns = [c for c in columns if c != "asset_id"]
            placeholders = ", ".join("?" for _ in columns)
            col_sql = ", ".join(columns)
            connection.execute(
                f"INSERT INTO assets ({col_sql}) VALUES ({placeholders})",
                [item[c] for c in columns],
            )
            imported["assets"] += 1

        # metadata (unique key)
        for item in payload.get("metadata", []):
            key = item["key"]
            existing = connection.execute(
                "SELECT 1 FROM metadata WHERE key = ?", (key,)
            ).fetchone()
            if existing is not None and on_conflict == "skip":
                skipped["metadata"] += 1
                continue
            if existing is not None and on_conflict == "overwrite":
                connection.execute("DELETE FROM metadata WHERE key = ?", (key,))
            columns = list(item.keys())
            placeholders = ", ".join("?" for _ in columns)
            col_sql = ", ".join(columns)
            connection.execute(
                f"INSERT INTO metadata ({col_sql}) VALUES ({placeholders})",
                [item[c] for c in columns],
            )
            imported["metadata"] += 1

        connection.commit()
    finally:
        connection.close()

    return {"imported": sum(imported.values()), "skipped": sum(skipped.values())}