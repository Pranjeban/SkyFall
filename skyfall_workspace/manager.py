"""Local workspace registry and metadata-only index for SKYFALL v0.9."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .analyzer import (
    EXCLUDED_FILE_NAMES,
    EXCLUDED_SUFFIXES,
    SUPPORTED_EXTENSIONS,
    analyze_file,
    detect_sensitive_content,
)


EXCLUDED_DIR_NAMES = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "dist", "build", "bin", "obj", ".idea", ".vs", "packages",
    # Credential stores, key material and cloud CLI profiles are outside the
    # intended source-indexing scope for this release.
    ".ssh", ".azure", ".aws", ".kube", ".gnupg", ".docker",
    ".terraform", ".terraform.d", ".pulumi", "credentials", "secrets",
    "certificates", "certificate", "certs", "private", "private_keys", "keys",
}
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILES_PER_WORKSPACE = 20000
MAX_TOTAL_SCAN_BYTES = 512 * 1024 * 1024
MAX_SCAN_DEPTH = 24
MAX_QUERY_LENGTH = 200


@dataclass(frozen=True)
class WorkspaceRecord:
    id: str
    path: str
    display_name: str
    enabled: bool
    allow_ai_metadata: bool
    added_at: str
    last_scan_at: str | None
    scan_status: str
    file_count: int
    skipped_count: int
    scan_error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "display_name": self.display_name,
            "enabled": self.enabled,
            "allow_ai_metadata": self.allow_ai_metadata,
            "added_at": self.added_at,
            "last_scan_at": self.last_scan_at,
            "scan_status": self.scan_status,
            "file_count": self.file_count,
            "skipped_count": self.skipped_count,
            "scan_error": self.scan_error,
        }


@dataclass(frozen=True)
class ScanFile:
    file_id: str
    workspace_id: str
    relative_path: str
    absolute_path: str
    name: str
    extension: str
    language: str
    kind: str
    size_bytes: int
    modified_at: str
    sha256: str
    summary: str
    parameters: list[str]
    functions: list[str]
    classes: list[str]
    imports: list[str]
    commands: list[str]
    top_level_keys_or_headings: list[str]
    parse_status: str
    sensitive_flag: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "workspace_id": self.workspace_id,
            "relative_path": self.relative_path,
            "absolute_path": self.absolute_path,
            "name": self.name,
            "extension": self.extension,
            "language": self.language,
            "kind": self.kind,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "sha256": self.sha256,
            "summary": self.summary,
            "parameters": self.parameters,
            "functions": self.functions,
            "classes": self.classes,
            "imports": self.imports,
            "commands": self.commands,
            "top_level_keys_or_headings": self.top_level_keys_or_headings,
            "parse_status": self.parse_status,
            "sensitive_flag": self.sensitive_flag,
        }


class WorkspaceManager:
    """SQLite-backed workspace registry and local index.

    Workspace roots are explicitly added by the user. Indexing is read-only,
    excludes secrets and reparse points, and stores extracted metadata only;
    source file contents are never persisted or returned by MCP tools.
    """

    def __init__(self, database_path: str | Path | None = None) -> None:
        if database_path is None:
            local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home()))
            database_path = local_app_data / "SKYFALL" / "data" / "workspace_index.db"
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=20000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    path_key TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    allow_ai_metadata INTEGER NOT NULL DEFAULT 0,
                    added_at TEXT NOT NULL,
                    last_scan_at TEXT,
                    scan_status TEXT NOT NULL DEFAULT 'not_scanned',
                    file_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    scan_error TEXT
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS workspace_files (
                    file_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    absolute_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    language TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    modified_at TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    functions_json TEXT NOT NULL,
                    classes_json TEXT NOT NULL,
                    imports_json TEXT NOT NULL,
                    commands_json TEXT NOT NULL,
                    headings_json TEXT NOT NULL,
                    parse_status TEXT NOT NULL,
                    sensitive_flag INTEGER NOT NULL DEFAULT 0,
                    indexed_at TEXT NOT NULL,
                    UNIQUE(workspace_id, relative_path),
                    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workspace_files_name ON workspace_files(name COLLATE NOCASE)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workspace_files_workspace ON workspace_files(workspace_id)"
            )

    @staticmethod
    def _normalize_root(path: str | Path) -> Path:
        candidate = Path(path).expanduser().resolve(strict=True)
        if not candidate.is_dir():
            raise ValueError("Selected workspace path is not a directory.")
        if candidate == Path(candidate.anchor):
            raise ValueError("For safety, SKYFALL cannot index an entire drive. Select a specific engineering folder.")
        home = Path.home().resolve()
        if candidate == home or candidate in home.parents:
            raise ValueError("For safety, select a specific folder inside your profile rather than your entire user profile or its parent.")
        protected_values = [
            os.environ.get("WINDIR"),
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("ProgramData"),
        ]
        for value in protected_values:
            if not value:
                continue
            protected = Path(value).expanduser().resolve()
            if candidate == protected or protected in candidate.parents:
                raise ValueError("SKYFALL does not index Windows or installed-application directories. Select an engineering workspace.")
        return candidate

    def add_workspace(self, path: str | Path, allow_ai_metadata: bool = False) -> WorkspaceRecord:
        root = self._normalize_root(path)
        now = self._now()
        path_key = os.path.normcase(str(root))
        workspace_id: str
        with self._connection() as conn:
            existing = conn.execute(
                "SELECT id FROM workspaces WHERE path_key=?", (path_key,)
            ).fetchone()
            if existing is not None:
                workspace_id = str(existing["id"])
            else:
                workspace_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO workspaces
                       (id, path, path_key, display_name, enabled, allow_ai_metadata, added_at)
                       VALUES (?, ?, ?, ?, 1, ?, ?)""",
                    (
                        workspace_id,
                        str(root),
                        path_key,
                        root.name or str(root),
                        1 if allow_ai_metadata else 0,
                        now,
                    ),
                )
        record = self.get_workspace(workspace_id)
        if record is None:
            raise RuntimeError("Workspace record could not be loaded after registration.")
        return record

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT w.*, COUNT(f.file_id) AS indexed_count
                   FROM workspaces w LEFT JOIN workspace_files f ON f.workspace_id=w.id
                   WHERE w.id=? GROUP BY w.id""",
                (workspace_id,),
            ).fetchone()
        return self._workspace_from_row(row) if row else None

    def list_workspaces(self, include_disabled: bool = True) -> list[WorkspaceRecord]:
        query = """SELECT w.*, COUNT(f.file_id) AS indexed_count
                   FROM workspaces w LEFT JOIN workspace_files f ON f.workspace_id=w.id"""
        if not include_disabled:
            query += " WHERE w.enabled=1"
        query += " GROUP BY w.id ORDER BY w.display_name COLLATE NOCASE"
        with self._connection() as conn:
            rows = conn.execute(query).fetchall()
        return [self._workspace_from_row(row) for row in rows]

    @staticmethod
    def _workspace_from_row(row: sqlite3.Row) -> WorkspaceRecord:
        return WorkspaceRecord(
            id=row["id"],
            path=row["path"],
            display_name=row["display_name"],
            enabled=bool(row["enabled"]),
            allow_ai_metadata=bool(row["allow_ai_metadata"]),
            added_at=row["added_at"],
            last_scan_at=row["last_scan_at"],
            scan_status=row["scan_status"],
            file_count=int(row["indexed_count"]),
            skipped_count=int(row["skipped_count"]),
            scan_error=row["scan_error"],
        )

    def set_workspace_enabled(self, workspace_id: str, enabled: bool) -> None:
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE workspaces SET enabled=? WHERE id=?",
                (1 if enabled else 0, workspace_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Workspace not found: {workspace_id}")

    def set_ai_metadata_access(self, workspace_id: str, enabled: bool) -> None:
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE workspaces SET allow_ai_metadata=? WHERE id=?",
                (1 if enabled else 0, workspace_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Workspace not found: {workspace_id}")

    def remove_workspace(self, workspace_id: str) -> None:
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM workspaces WHERE id=?", (workspace_id,))
            if cursor.rowcount == 0:
                raise KeyError(f"Workspace not found: {workspace_id}")

    @staticmethod
    def _is_reparse_point(path: Path) -> bool:
        try:
            info = path.lstat()
            attrs = getattr(info, "st_file_attributes", 0)
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            return path.is_symlink() or bool(attrs & reparse_flag)
        except OSError:
            return True

    @staticmethod
    def _excluded_file(path: Path) -> bool:
        name = path.name.lower()
        suffix = path.suffix.lower()
        if name in EXCLUDED_FILE_NAMES or suffix in EXCLUDED_SUFFIXES:
            return True
        if name == ".env" or name.startswith(".env."):
            return True
        if name in {"secrets", "credentials", "service-account", "service_account"}:
            return True
        if name.endswith((".secret.json", ".credentials.json", ".token.json")):
            return True
        return False

    def _collect_index_files(self, workspace_id: str, root: Path) -> tuple[list[dict[str, Any]], int, bool]:
        records: list[dict[str, Any]] = []
        skipped = 0
        truncated = False
        total_read_bytes = 0
        root_resolved = root.resolve(strict=True)
        stack: list[tuple[Path, int]] = [(root_resolved, 0)]

        while stack:
            directory, depth = stack.pop()
            if depth > MAX_SCAN_DEPTH or self._is_reparse_point(directory):
                skipped += 1
                continue
            try:
                entries = list(os.scandir(directory))
            except (PermissionError, OSError):
                skipped += 1
                continue

            for entry in entries:
                path = Path(entry.path)
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.lower() in EXCLUDED_DIR_NAMES or self._is_reparse_point(path):
                            skipped += 1
                            continue
                        resolved_dir = path.resolve(strict=True)
                        if not resolved_dir.is_relative_to(root_resolved):
                            skipped += 1
                            continue
                        stack.append((resolved_dir, depth + 1))
                        continue

                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if self._is_reparse_point(path) or self._excluded_file(path):
                        skipped += 1
                        continue
                    extension = path.suffix.lower()
                    if extension not in SUPPORTED_EXTENSIONS:
                        continue

                    stat_result = entry.stat(follow_symlinks=False)
                    if stat_result.st_size <= 0 or stat_result.st_size > MAX_FILE_BYTES:
                        skipped += 1
                        continue
                    if total_read_bytes + stat_result.st_size > MAX_TOTAL_SCAN_BYTES:
                        truncated = True
                        return records, skipped, truncated
                    resolved_file = path.resolve(strict=True)
                    if not resolved_file.is_relative_to(root_resolved):
                        skipped += 1
                        continue
                    raw = resolved_file.read_bytes()
                    total_read_bytes += len(raw)
                    if b"\x00" in raw:
                        skipped += 1
                        continue
                    try:
                        text = raw.decode("utf-8-sig")
                    except UnicodeDecodeError:
                        try:
                            text = raw.decode("cp1252")
                        except UnicodeDecodeError:
                            skipped += 1
                            continue

                    sensitive = detect_sensitive_content(text)
                    metadata = analyze_file(resolved_file, text)
                    rel = resolved_file.relative_to(root_resolved).as_posix()
                    file_id = hashlib.sha256(
                        f"{workspace_id}:{rel.casefold()}".encode("utf-8")
                    ).hexdigest()[:32]
                    modified = datetime.fromtimestamp(
                        stat_result.st_mtime, tz=timezone.utc
                    ).isoformat(timespec="seconds")
                    records.append({
                        "file_id": file_id,
                        "workspace_id": workspace_id,
                        "relative_path": rel,
                        "absolute_path": str(resolved_file),
                        "name": resolved_file.name,
                        "extension": extension,
                        "language": metadata["language"],
                        "kind": metadata["kind"],
                        "size_bytes": int(stat_result.st_size),
                        "modified_at": modified,
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "summary": metadata["summary"],
                        "parameters": metadata["parameters"],
                        "functions": metadata["functions"],
                        "classes": metadata["classes"],
                        "imports": metadata["imports"],
                        "commands": metadata["commands"],
                        "headings": metadata["top_level_keys_or_headings"],
                        "parse_status": metadata["parse_status"],
                        "sensitive_flag": 1 if sensitive else 0,
                    })

                    if len(records) >= MAX_FILES_PER_WORKSPACE:
                        truncated = True
                        return records, skipped, truncated
                except (PermissionError, OSError, ValueError):
                    skipped += 1
                    continue

        return records, skipped, truncated

    def scan_workspace(self, workspace_id: str) -> dict[str, Any]:
        workspace = self.get_workspace(workspace_id)
        if workspace is None:
            raise KeyError(f"Workspace not found: {workspace_id}")
        if not workspace.enabled:
            raise PermissionError("Workspace is disabled and cannot be scanned.")
        root = Path(workspace.path)
        if not root.is_dir():
            with self._connection() as conn:
                conn.execute(
                    "UPDATE workspaces SET scan_status='failed', scan_error=? WHERE id=?",
                    ("Workspace folder is unavailable.", workspace_id),
                )
            raise FileNotFoundError("Workspace folder is unavailable.")

        try:
            records, skipped, truncated = self._collect_index_files(workspace_id, root)
            now = self._now()
            with self._connection() as conn:
                conn.execute("DELETE FROM workspace_files WHERE workspace_id=?", (workspace_id,))
                for row in records:
                    conn.execute(
                        """INSERT INTO workspace_files (
                            file_id, workspace_id, relative_path, absolute_path, name,
                            extension, language, kind, size_bytes, modified_at, sha256,
                            summary, parameters_json, functions_json, classes_json,
                            imports_json, commands_json, headings_json, parse_status,
                            sensitive_flag, indexed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            row["file_id"], row["workspace_id"], row["relative_path"],
                            row["absolute_path"], row["name"], row["extension"],
                            row["language"], row["kind"], row["size_bytes"],
                            row["modified_at"], row["sha256"], row["summary"],
                            json.dumps(row["parameters"]), json.dumps(row["functions"]),
                            json.dumps(row["classes"]), json.dumps(row["imports"]),
                            json.dumps(row["commands"]), json.dumps(row["headings"]),
                            row["parse_status"], row["sensitive_flag"], now,
                        ),
                    )
                conn.execute(
                    """UPDATE workspaces SET last_scan_at=?, scan_status=?,
                       file_count=?, skipped_count=?, scan_error=NULL WHERE id=?""",
                    (now, "truncated" if truncated else "complete", len(records), skipped, workspace_id),
                )
            return {
                "workspace_id": workspace_id,
                "display_name": workspace.display_name,
                "indexed_files": len(records),
                "skipped_files": skipped,
                "truncated": truncated,
                "scan_status": "truncated" if truncated else "complete",
                "last_scan_at": now,
                "metadata_storage": "local_only",
                "source_contents_persisted": False,
            }
        except Exception as exc:
            with self._connection() as conn:
                conn.execute(
                    "UPDATE workspaces SET scan_status='failed', scan_error=? WHERE id=?",
                    (f"{type(exc).__name__}: {exc}"[:1000], workspace_id),
                )
            raise

    def scan_all(self) -> list[dict[str, Any]]:
        results = []
        for workspace in self.list_workspaces(include_disabled=False):
            try:
                results.append(self.scan_workspace(workspace.id))
            except Exception as exc:
                results.append({
                    "workspace_id": workspace.id,
                    "display_name": workspace.display_name,
                    "scan_status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                })
        return results

    @staticmethod
    def _file_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "file_id": row["file_id"],
            "workspace_id": row["workspace_id"],
            "workspace_name": row["display_name"],
            "workspace_path": row["workspace_path"],
            "relative_path": row["relative_path"],
            "absolute_path": row["absolute_path"],
            "name": row["name"],
            "extension": row["extension"],
            "language": row["language"],
            "kind": row["kind"],
            "size_bytes": int(row["size_bytes"]),
            "modified_at": row["modified_at"],
            "sha256": row["sha256"],
            "summary": row["summary"],
            "parameters": json.loads(row["parameters_json"]),
            "functions": json.loads(row["functions_json"]),
            "classes": json.loads(row["classes_json"]),
            "imports": json.loads(row["imports_json"]),
            "commands": json.loads(row["commands_json"]),
            "top_level_keys_or_headings": json.loads(row["headings_json"]),
            "parse_status": row["parse_status"],
            "sensitive_flag": bool(row["sensitive_flag"]),
        }

    def _search(self, query: str, file_type: str = "all", workspace_id: str | None = None,
                limit: int = 20, ai_only: bool = False) -> list[dict[str, Any]]:
        clean_query = (query or "").strip()
        if not clean_query or len(clean_query) > MAX_QUERY_LENGTH:
            raise ValueError(f"Search query must contain 1 to {MAX_QUERY_LENGTH} characters.")
        safe_limit = max(1, min(int(limit), 50))
        clean_type = (file_type or "all").strip().lower()
        if clean_type not in {"all", "scripts", "documents", "powershell", "python", "yaml", "json", "markdown"}:
            raise ValueError("Unsupported file_type filter.")

        conditions = ["w.enabled=1", "f.sensitive_flag=0"]
        params: list[Any] = []
        if ai_only:
            conditions.append("w.allow_ai_metadata=1")
        if workspace_id:
            conditions.append("w.id=?")
            params.append(workspace_id)
        if clean_type == "scripts":
            conditions.append("f.kind='script'")
        elif clean_type == "documents":
            conditions.append("f.kind='document_or_config'")
        elif clean_type == "powershell":
            conditions.append("f.extension IN ('.ps1','.psm1','.psd1')")
        elif clean_type == "python":
            conditions.append("f.extension='.py'")
        elif clean_type == "yaml":
            conditions.append("f.extension IN ('.yaml','.yml')")
        elif clean_type == "json":
            conditions.append("f.extension='.json'")
        elif clean_type == "markdown":
            conditions.append("f.extension='.md'")

        terms = [t for t in re.split(r"\s+", clean_query) if t]
        for term in terms[:8]:
            like = f"%{term}%"
            conditions.append(
                "(f.name LIKE ? COLLATE NOCASE OR f.relative_path LIKE ? COLLATE NOCASE "
                "OR f.summary LIKE ? COLLATE NOCASE OR f.language LIKE ? COLLATE NOCASE "
                "OR f.parameters_json LIKE ? COLLATE NOCASE OR f.functions_json LIKE ? COLLATE NOCASE "
                "OR f.imports_json LIKE ? COLLATE NOCASE OR f.commands_json LIKE ? COLLATE NOCASE)"
            )
            params.extend([like] * 8)

        sql = """SELECT f.*, w.display_name, w.path AS workspace_path
                 FROM workspace_files f JOIN workspaces w ON w.id=f.workspace_id
                 WHERE """ + " AND ".join(conditions) + " ORDER BY f.name COLLATE NOCASE LIMIT ?"
        params.append(safe_limit)
        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._file_from_row(row) for row in rows]

    def search_local(self, query: str, file_type: str = "all", workspace_id: str | None = None,
                     limit: int = 50) -> list[dict[str, Any]]:
        """Local desktop search; does not disclose results to Copilot."""
        return self._search(query, file_type, workspace_id, limit, ai_only=False)

    def search_for_ai(self, query: str, file_type: str = "all", workspace_id: str | None = None,
                      limit: int = 20) -> list[dict[str, Any]]:
        """Search only workspaces for which the user explicitly enabled AI metadata sharing."""
        return self._search(query, file_type, workspace_id, limit, ai_only=True)

    def list_for_ai(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT w.*, COUNT(f.file_id) AS indexed_count
                   FROM workspaces w LEFT JOIN workspace_files f ON f.workspace_id=w.id
                   WHERE w.enabled=1 AND w.allow_ai_metadata=1
                   GROUP BY w.id ORDER BY w.display_name COLLATE NOCASE"""
            ).fetchall()
        return [self._workspace_from_row(row).to_dict() for row in rows]

    def describe_file_for_ai(self, file_id: str) -> dict[str, Any]:
        if not file_id or len(file_id) > 80:
            raise ValueError("A valid file_id is required.")
        with self._connection() as conn:
            row = conn.execute(
                """SELECT f.*, w.display_name, w.path AS workspace_path
                   FROM workspace_files f JOIN workspaces w ON w.id=f.workspace_id
                   WHERE f.file_id=? AND w.enabled=1 AND w.allow_ai_metadata=1
                   AND f.sensitive_flag=0""",
                (file_id,),
            ).fetchone()
        if row is None:
            raise KeyError("File not found, not indexed, or workspace metadata sharing is not enabled.")
        return self._file_from_row(row)

    def get_ai_index_status(self) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT COUNT(DISTINCT w.id) AS workspace_count,
                          COUNT(f.file_id) AS file_count,
                          SUM(CASE WHEN f.sensitive_flag=1 THEN 1 ELSE 0 END) AS sensitive_count
                   FROM workspaces w LEFT JOIN workspace_files f ON f.workspace_id=w.id
                   WHERE w.enabled=1 AND w.allow_ai_metadata=1"""
            ).fetchone()
        return {
            "ai_visible_workspaces": int(row["workspace_count"] or 0),
            "ai_searchable_files": int(row["file_count"] or 0) - int(row["sensitive_count"] or 0),
            "sensitive_files_excluded": int(row["sensitive_count"] or 0),
            "source_contents_shared": False,
            "scope": "only enabled workspaces with explicit AI metadata sharing consent",
        }
