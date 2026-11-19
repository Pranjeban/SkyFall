"""Cross-platform intelligence (Phase 7)."""

from __future__ import annotations

from typing import Any


class CrossPlatformService:
    def compare_configurations(self, azure_items: list[dict[str, Any]], pp_items: list[dict[str, Any]], key: str = "name") -> dict[str, Any]:
        a = {str(i.get(key)): i for i in azure_items if isinstance(i, dict)}
        b = {str(i.get(key)): i for i in pp_items if isinstance(i, dict)}
        common = sorted(set(a) & set(b))
        only_a = sorted(set(a) - set(b))
        only_b = sorted(set(b) - set(a))
        drift = []
        for name in common:
            if a[name] != b[name]:
                drift.append({"name": name, "azure": a[name], "powerplatform": b[name]})
        return {"common": common, "only_azure": only_a, "only_powerplatform": only_b,
                "drift_count": len(drift), "drift": drift}
