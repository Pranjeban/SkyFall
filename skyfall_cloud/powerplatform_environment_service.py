"""Power Platform environment intelligence (Phase 4)."""

from __future__ import annotations

import json
from typing import Any

from .azure_profiles import AzureProfileManager


class PowerPlatformEnvironmentService:
    def __init__(self, manager: AzureProfileManager | None = None) -> None:
        self.manager = manager or AzureProfileManager()

    def compare_environments(self, env_a: dict[str, Any], env_b: dict[str, Any]) -> dict[str, Any]:
        keys = sorted(set(env_a) | set(env_b))
        differences = []
        for key in keys:
            if env_a.get(key) != env_b.get(key):
                differences.append({"field": key, "a": env_a.get(key), "b": env_b.get(key)})
        return {"environment_a": env_a.get("name"), "environment_b": env_b.get("name"),
                "difference_count": len(differences), "differences": differences}

    def environment_health(self, env: dict[str, Any]) -> dict[str, Any]:
        status = str(env.get("properties", {}).get("states", {}).get("management", {}).get("id", "") or env.get("state", "unknown"))
        return {"name": env.get("name") or env.get("displayName"), "state": status,
                "has_dataverse": bool(env.get("properties", {}).get("linkedEnvironmentMetadata", {}).get("instanceUrl")),
                "region": env.get("location") or env.get("properties", {}).get("location")}
