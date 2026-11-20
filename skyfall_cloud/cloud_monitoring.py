"""Monitoring and anomaly detection (v1.1 Module 7).

Read-only analysis of records already collected by the discovery and inventory
services. No HTTP, credentials or live tenant access is used. Timestamps are
parsed defensively: malformed or missing values are skipped, never fatal.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def parse_timestamp(value: Any) -> datetime | None:
    """Return a timezone-aware UTC datetime, or None for unusable values."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class CloudMonitoringService:
    """Deterministic anomaly detectors over flat inventory records."""

    @staticmethod
    def _rows(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, (list, tuple)):
            return [row for row in value if isinstance(row, dict)]
        return []

    def detect_inactive(
        self,
        items: Any,
        last_used_field: str = "lastUsed",
        days: int = 30,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Items whose last-used timestamp is older than ``days``."""
        return self.detect_stale(items, last_used_field, days, now=now)

    def detect_stale(
        self,
        items: Any,
        timestamp_field: str,
        days: int = 30,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        cutoff = reference - timedelta(days=max(0, int(days)))
        stale: list[dict[str, Any]] = []
        for row in self._rows(items):
            parsed = parse_timestamp(row.get(timestamp_field))
            if parsed is not None and parsed < cutoff:
                stale.append(dict(row))
        return stale

    def detect_state_anomalies(
        self,
        items: Any,
        state_field: str = "state",
        unhealthy_states: Any = ("error", "failed", "disconnected", "stopped"),
    ) -> list[dict[str, Any]]:
        unhealthy = {str(value).strip().lower() for value in unhealthy_states}
        flagged: list[dict[str, Any]] = []
        for row in self._rows(items):
            state = str(row.get(state_field) or "").strip().lower()
            if state in unhealthy:
                flagged.append(dict(row))
        return flagged

    def detect_duplicates(self, items: Any, key_field: str) -> list[dict[str, Any]]:
        seen: dict[str, int] = {}
        for row in self._rows(items):
            key = str(row.get(key_field) or "").strip()
            if key:
                seen[key] = seen.get(key, 0) + 1
        return [
            {"key": key, "count": count}
            for key, count in sorted(seen.items())
            if count > 1
        ]

    def health_report(
        self,
        azure_resources: Any = (),
        pp_environments: Any = (),
        pp_flows: Any = (),
        pp_connections: Any = (),
        now: datetime | None = None,
    ) -> dict[str, Any]:
        flows = self._rows(pp_flows)
        connections = self._rows(pp_connections)
        anomalies = {
            "inactive_resources": len(
                self.detect_inactive(azure_resources, now=now)
            ),
            "unhealthy_flows": len(self.detect_state_anomalies(flows)),
            "broken_connections": len(self.detect_state_anomalies(connections)),
            "duplicate_environments": len(
                self.detect_duplicates(pp_environments, "environment_id")
            ),
        }
        total = sum(anomalies.values())
        if total == 0:
            severity = "healthy"
        elif total <= 3:
            severity = "warning"
        else:
            severity = "critical"
        return {
            "success": True,
            "severity": severity,
            "anomaly_count": total,
            "anomalies": anomalies,
            "counts": {
                "azure_resources": len(self._rows(azure_resources)),
                "pp_environments": len(self._rows(pp_environments)),
                "pp_flows": len(flows),
                "pp_connections": len(connections),
            },
            "token_material_returned": False,
        }
