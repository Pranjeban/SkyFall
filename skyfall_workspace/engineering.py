"""Engineering intelligence helpers for SKYFALL workspaces (read-only)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def analyze_workspace(root: str | Path) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    files = []
    duplicates: dict[str, list[str]] = {}
    hashes: dict[str, list[str]] = {}
    for path in base.rglob("*"):
        if path.is_file():
            try:
                data = path.read_bytes()
            except OSError:
                continue
            digest = hashlib.sha256(data).hexdigest()
            hashes.setdefault(digest, []).append(str(path))
            files.append({"path": str(path), "size": len(data), "sha256": digest})
    for digest, paths in hashes.items():
        if len(paths) > 1:
            duplicates[digest] = paths
    return {
        "root": str(base),
        "file_count": len(files),
        "files": files[:1000],
        "duplicate_groups": duplicates,
        "success": True,
    }


def search_workspaces(roots: list[str | Path], query: str) -> list[dict[str, Any]]:
    q = query.lower()
    results = []
    for root in roots:
        base = Path(root).expanduser().resolve()
        for path in base.rglob("*"):
            if path.is_file() and q in path.name.lower():
                results.append({"path": str(path), "workspace": str(base)})
    return results
