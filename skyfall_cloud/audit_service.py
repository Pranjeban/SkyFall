"""Audit, security & execution governance (Phase 12)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class AuditService:
    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def record(self, action: str, actor: str, target: str, params: Any = None, result: str = "ok") -> dict[str, Any]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            "action": action,
            "actor": actor,
            "target": target,
            "params_hash": hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest() if params is not None else None,
            "result": result,
        }
        self._entries.append(entry)
        return entry

    def history(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def export_json(self) -> str:
        return json.dumps(self._entries, indent=2, default=str)
