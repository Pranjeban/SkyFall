"""Azure resource inventory service (Phase 3).

Uses Azure CLI (az resource list / az graph) for dynamic resource discovery.
No credentials or tokens are stored; reads only.
"""

from __future__ import annotations

import json
from typing import Any

from .azure_profiles import AzureProfileManager


class AzureResourceInventory:
    def __init__(self, manager: AzureProfileManager | None = None) -> None:
        self.manager = manager or AzureProfileManager()

    def list_resources(self, profile_id: str = "all", resource_type: str | None = None, location: str | None = None) -> dict[str, Any]:
        clean = (profile_id or "all").strip()
        if clean.lower() not in {"all", "*"}:
            return self._single(clean, resource_type, location)
        results = [self._single(p["profile_id"], resource_type, location) for p in self.manager.store.list_profiles()]
        merged = []
        for r in results:
            if r.get("success"):
                for item in r.get("resources", []):
                    merged.append({**item, "profile_id": r.get("profile_id"), "profile": r.get("profile")})
        errors = [{"profile_id": r.get("profile_id"), "error": r.get("error")} for r in results if not r.get("success")]
        ok = sum(1 for r in results if r.get("success"))
        return {"success": ok > 0, "profile_id": "all", "count": len(merged), "resources": merged,
                "failed_profiles": errors, "partial_success": ok > 0 and bool(errors)}

    def _single(self, profile_id: str, resource_type: str | None, location: str | None) -> dict[str, Any]:
        profile = self.manager.store.get_profile(profile_id)
        args = ["resource", "list", "--output", "json"]
        if resource_type:
            args += ["--resource-type", resource_type]
        if location:
            args += ["--location", location]
        try:
            result = self.manager.runner("az", args, timeout_seconds=120, env_overrides=self.manager._env_for(profile_id))
        except FileNotFoundError as exc:
            return {"success": False, "profile_id": profile_id, "error": str(exc), "resources": []}
        if not result.succeeded:
            return {"success": False, "profile_id": profile_id, "profile": profile["name"],
                    "error": (result.stderr.strip() or "resource list failed")[:800], "resources": []}
        try:
            entries = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as exc:
            return {"success": False, "profile_id": profile_id, "profile": profile["name"], "error": str(exc), "resources": []}
        if not isinstance(entries, list):
            return {"success": False, "profile_id": profile_id, "profile": profile["name"], "error": "unexpected response", "resources": []}
        safe = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            safe.append({
                "profile": profile["name"], "profile_id": profile_id,
                "id": str(item.get("id", "") or ""),
                "name": str(item.get("name", "") or ""),
                "type": str(item.get("type", "") or ""),
                "location": str(item.get("location", "") or ""),
                "resource_group": str(item.get("resourceGroup", "") or ""),
                "tags": item.get("tags") if isinstance(item.get("tags"), dict) else {},
            })
        return {"success": True, "profile_id": profile_id, "profile": profile["name"], "count": len(safe), "resources": safe}
