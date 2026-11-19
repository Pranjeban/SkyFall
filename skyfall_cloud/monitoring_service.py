"""Monitoring and anomaly detection (Phase 8)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class MonitoringService:
    def detect_inactive(self, items: list[dict[str, Any]], last_used_field: str = "lastUsed", days: int = 30) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        inactive = []
        for item in items:
            raw = item.get(last_used_field)
            if not raw:
                inactive.append({**item, "reason": "no usage timestamp"})
                continue
            try:
                ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if (now - ts).days >= days:
                    inactive.append({**item, "reason": f"inactive for {(now - ts).days} days"})
            except ValueError:
                inactive.append({**item, "reason": "unparseable timestamp"})
        return inactive

    def detect_cost_anomaly(self, series: list[float], threshold: float = 0.2) -> list[dict[str, Any]]:
        if len(series) < 2:
            return []
        anomalies = []
        for i in range(1, len(series)):
            prev = series[i - 1] or 1
            change = (series[i] - prev) / prev
            if abs(change) >= threshold:
                anomalies.append({"index": i, "value": series[i], "change_percent": round(change * 100, 2)})
        return anomalies
