"""Audit, security and governance (v1.1 Module 11).

In-memory append-only audit of read-only tool calls plus a conservative policy
gate. No disk or database persistence, no network, no credential storage. All
returned entries are copies and every string is redacted before storage.
"""

from __future__ import annotations

import copy
import re
import threading
from datetime import datetime, timezone
from typing import Any

_SENSITIVE_WORDS = (
    "token", "secret", "password", "credential", "authorization", "connectionstring",
)
_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._\-+/=]{8,}", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[A-Za-z0-9._\-]{12,}")
_REDACTED = "[REDACTED]"
_READ_VERBS = frozenset({
    "list", "get", "describe", "inspect", "compare", "discover", "query",
    "summarize", "build", "simulate", "health", "inventory",
})
_DENIED_VERBS = (
    "delete", "remove", "destroy", "drop", "purge", "kill", "terminate",
    "execute", "run", "modify", "update", "create", "write", "set",
    "disable", "enable", "restart", "stop", "start", "deploy", "grant",
    "revoke", "reset", "assign", "move", "copy", "publish",
)


class CloudGovernanceService:
    """Thread-safe in-memory governance ledger and policy evaluator."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._sequence = 0

    @staticmethod
    def redact(value: Any) -> Any:
        """Recursively redact sensitive keys and token-like values (idempotent)."""
        if isinstance(value, dict):
            return {
                key: _REDACTED if CloudGovernanceService._sensitive_key(key)
                else CloudGovernanceService.redact(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [CloudGovernanceService.redact(item) for item in value]
        if isinstance(value, str):
            cleaned = _BEARER.sub(f"Bearer {_REDACTED}", value)
            return _JWT.sub(_REDACTED, cleaned)
        return value

    @staticmethod
    def _sensitive_key(name: Any) -> bool:
        lower = str(name).lower()
        if any(word in lower for word in _SENSITIVE_WORDS):
            return True
        return "key" in set(re.split(r"[^a-z0-9]+", lower))

    def record(
        self,
        event: str,
        *,
        profile_id: str | None = None,
        provider: str | None = None,
        action: str = "",
        outcome: str = "",
        details: Any = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._sequence += 1
            entry = {
                "sequence": self._sequence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": self.redact(str(event or "")[:200]),
                "profile_id": self.redact(str(profile_id or "")[:200]) or None,
                "provider": self.redact(str(provider or "")[:50]) or None,
                "action": self.redact(str(action or "")[:200]),
                "outcome": self.redact(str(outcome or "")[:200]),
                "details": self.redact(details),
            }
            self._entries.append(entry)
            return copy.deepcopy(entry)

    def entries(
        self,
        *,
        event: str | None = None,
        provider: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = copy.deepcopy(self._entries)
        if event is not None:
            rows = [row for row in rows if row["event"] == event]
        if provider is not None:
            rows = [row for row in rows if row["provider"] == provider]
        if limit is not None:
            rows = rows[: max(0, int(limit))]
        return rows

    def evaluate_policy(
        self,
        operation: str,
        *,
        provider: str | None = None,
        profile_provider: str | None = None,
        profile_id: str | None = None,
        requires_approval: bool = False,
    ) -> dict[str, Any]:
        op = str(operation or "").strip().lower()
        tokens = set(re.split(r"[^a-z0-9]+", op))
        reasons: list[str] = []
        destructive = any(verb in tokens or verb in op for verb in _DENIED_VERBS)
        read_only = bool(tokens & _READ_VERBS) and not destructive
        if destructive:
            reasons.append("Operation contains a mutating or executing verb.")
        if not read_only and not destructive:
            reasons.append("Operation is not on the read-only allowlist.")
        if provider and profile_provider and provider != profile_provider:
            reasons.append("Operation provider does not match the selected profile provider.")
        allowed = not reasons
        return {
            "allowed": allowed,
            "requires_approval": bool(destructive or requires_approval),
            "reasons": reasons,
            "operation": self.redact(op[:200]),
            "provider": self.redact(provider),
            "profile_id": self.redact(profile_id),
        }

    def summary(self) -> dict[str, Any]:
        with self._lock:
            rows = list(self._entries)
        by_event: dict[str, int] = {}
        by_outcome: dict[str, int] = {}
        by_provider: dict[str, int] = {}
        for row in rows:
            for key, target in (
                ("event", by_event), ("outcome", by_outcome), ("provider", by_provider)
            ):
                value = str(row.get(key) or "unknown")
                target[value] = target.get(value, 0) + 1
        return {
            "total": len(rows),
            "by_event": dict(sorted(by_event.items())),
            "by_outcome": dict(sorted(by_outcome.items())),
            "by_provider": dict(sorted(by_provider.items())),
        }
