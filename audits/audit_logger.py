"""Audit logger for SKYFALL operational traceability."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class AuditLogger:
    """Core audit logger for tracking system events."""

    def __init__(self, log_dir: Optional[str] = None, level: int = logging.INFO) -> None:
        self._log_dir = Path(log_dir) if log_dir else Path(__file__).resolve().parent.parent / "logs"
        self._level = level
        self._lock = threading.RLock()
        self._ensure_log_directory()
        self._setup_logging()
        self._last_entries: List[Dict[str, Any]] = []
        self._entry_count = 0

    def _ensure_log_directory(self) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _setup_logging(self) -> None:
        self._logger = logging.getLogger("AuditLogger")
        self._logger.setLevel(self._level)
        handler = logging.FileHandler(self._log_dir / "audit.log")
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(name)s] - %(message)s")
        handler.setFormatter(formatter)
        if not self._logger.handlers:
            self._logger.addHandler(handler)

    def _format_entry(self, event: Dict[str, Any]) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event.get("type"),
            "action": event.get("action"),
            "subject": event.get("subject"),
            "resource": event.get("resource"),
            "user": event.get("user"),
        }
        return json.dumps(entry, default=str)

    def log_event(
        self,
        event_type: str,
        action: Optional[str] = None,
        subject: Optional[str] = None,
        resource: Optional[str] = None,
        user: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        event: Dict[str, Any] = {
            "type": event_type,
            "action": action,
            "subject": subject,
            "resource": resource,
            "user": user,
        }
        event.update(extra)
        formatted = self._format_entry(event)
        with self._lock:
            self._logger.info(formatted)
            with open(self._log_dir / "audit_entries.jsonl", "a", encoding="utf-8") as f:
                f.write(formatted + "\n")
            self._last_entries.append(event)
            self._entry_count += 1
        return event

    def get_last_entries(self, count: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._last_entries[-count:])