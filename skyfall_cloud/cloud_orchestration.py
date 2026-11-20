"""Intelligent engineering orchestration (v1.1 Module 6).

Composes the read-only identity, Azure, Power Platform and catalog services into
one correlated report. Each step is isolated: a failure is recorded and the
remaining steps still run. Azure and Power Platform profiles are kept separate
so credentials can never cross providers.

No step writes to a cloud service. No token, secret or raw Microsoft error body
is returned: step errors are reduced to an exception type or a redacted string.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from skyfall_cloud.azure_discovery import AzureDiscoveryService
from skyfall_cloud.azure_graph_inventory import AzureResourceInventory
from skyfall_cloud.msal_identity import UnifiedIdentityAuthority
from skyfall_cloud.powerplatform_catalog import PowerPlatformCatalog
from skyfall_cloud.powerplatform_discovery import PowerPlatformDiscovery

_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._\-+/=]{8,}", re.IGNORECASE)
_LONG_SECRET = re.compile(r"\beyJ[A-Za-z0-9._\-]{12,}|\b[A-Za-z0-9]{40,}={0,2}\b")

TASK_GRAPH: tuple[dict[str, Any], ...] = (
    {"id": "identity_health", "module": "Module 4", "provider": "both",
     "description": "Secret-free unified identity health", "read_only": True},
    {"id": "azure_footprint", "module": "Module 2.1", "provider": "azure",
     "description": "Azure tenants, subscriptions and management groups", "read_only": True},
    {"id": "azure_inventory", "module": "Module 2.2/2.3", "provider": "azure",
     "description": "Azure Resource Graph inventory by category", "read_only": True},
    {"id": "pp_environments", "module": "Module 3.1", "provider": "powerplatform",
     "description": "Power Platform environment discovery", "read_only": True},
    {"id": "pp_catalog", "module": "Module 3.2-3.5", "provider": "powerplatform",
     "description": "Flow, app and connection inventory for one environment", "read_only": True},
)


class CloudOrchestrationService:
    """Read-only multi-step cloud investigation runner."""

    def __init__(
        self,
        *,
        identity: Any = None,
        azure_discovery: Any = None,
        azure_inventory: Any = None,
        pp_discovery: Any = None,
        pp_catalog: Any = None,
        now: Any = None,
    ) -> None:
        self._identity = identity
        self._azure_discovery = azure_discovery
        self._azure_inventory = azure_inventory
        self._pp_discovery = pp_discovery
        self._pp_catalog = pp_catalog
        self._now = now or (lambda: datetime.now(timezone.utc).isoformat())

    # -- lazy construction (only for steps actually run) -------------------

    def _get(self, name: str, factory: Any) -> Any:
        current = getattr(self, name)
        if current is None:
            current = factory()
            setattr(self, name, current)
        return current

    def _identity_service(self) -> Any:
        return self._get("_identity", UnifiedIdentityAuthority)

    def _azure_discovery_service(self) -> Any:
        return self._get("_azure_discovery", lambda: AzureDiscoveryService(self._identity_service()))

    def _azure_inventory_service(self) -> Any:
        return self._get("_azure_inventory", lambda: AzureResourceInventory(self._identity_service()))

    def _pp_discovery_service(self) -> Any:
        return self._get("_pp_discovery", lambda: PowerPlatformDiscovery(self._identity_service()))

    def _pp_catalog_service(self) -> Any:
        return self._get(
            "_pp_catalog",
            lambda: PowerPlatformCatalog(
                self._identity_service(),
                http_client=getattr(self._pp_discovery_service(), "http", None),
            ),
        )

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _safe_error(value: Any) -> str:
        if isinstance(value, BaseException):
            return type(value).__name__
        text = str(value or "")
        text = _BEARER.sub("Bearer [REDACTED]", text)
        text = _LONG_SECRET.sub("[REDACTED]", text)
        return text[:300]

    def task_graph(self) -> list[dict[str, Any]]:
        return [dict(step) for step in TASK_GRAPH]

    @staticmethod
    def _count(data: Any, *keys: str) -> int:
        if not isinstance(data, dict):
            return 0
        for key in keys:
            value = data.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, list):
                return len(value)
        return 0

    def _correlated(
        self,
        footprint: dict[str, Any],
        inventory: dict[str, Any],
        environments: dict[str, Any],
        flows: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "azure": {
                "tenants": self._count(footprint, "tenant_count", "tenants"),
                "subscriptions": self._count(footprint, "subscription_count", "subscriptions"),
                "resources": self._count(inventory, "count", "resources"),
            },
            "power_platform": {
                "environments": self._count(environments, "count", "environments"),
                "flows": self._count(flows, "count", "flows"),
            },
            "sessions_independent": True,
        }

    # -- runner -------------------------------------------------------------

    def run(
        self,
        *,
        azure_profile_id: str | None = None,
        pp_profile_id: str | None = None,
        subscription_ids: list[str] | None = None,
        categories: list[str] | None = None,
        environment_id: str | None = None,
    ) -> dict[str, Any]:
        """Run all read-only steps, isolating failures per step."""
        results: dict[str, dict[str, Any]] = {}

        def execute(step_id: str, action: Any) -> None:
            try:
                payload = action()
            except Exception as exc:  # noqa: BLE001 - isolated by design
                results[step_id] = {"success": False, "error": self._safe_error(exc), "data": None}
                return
            if isinstance(payload, dict) and payload.get("success") is False:
                results[step_id] = {
                    "success": False,
                    "error": self._safe_error(payload.get("error") or "Operation failed."),
                    "data": payload,
                }
                return
            results[step_id] = {"success": True, "error": None, "data": payload}

        execute("identity_health", lambda: self._identity_service().overall_health())
        execute(
            "azure_footprint",
            lambda: self._azure_discovery_service().tenant_subscription_overview(azure_profile_id),
        )
        if subscription_ids:
            execute(
                "azure_inventory",
                lambda: self._azure_inventory_service().inventory(
                    list(subscription_ids), categories=categories
                ),
            )
        else:
            results["azure_inventory"] = {
                "success": True, "error": None,
                "data": {"skipped": "No subscription IDs supplied.", "count": 0},
            }
        execute(
            "pp_environments",
            lambda: self._pp_discovery_service().list_environments(pp_profile_id),
        )

        selected_env = environment_id
        if not selected_env:
            env_data = results.get("pp_environments", {}).get("data") or {}
            rows = env_data.get("environments") if isinstance(env_data, dict) else None
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                selected_env = str(rows[0].get("environment_id") or "") or None
        if selected_env:
            execute(
                "pp_catalog",
                lambda: {
                    "flows": self._pp_catalog_service().list_flows(selected_env, pp_profile_id),
                    "apps": self._pp_catalog_service().list_apps(selected_env, pp_profile_id),
                    "connections": self._pp_catalog_service().list_connections(selected_env, pp_profile_id),
                },
            )
        else:
            results["pp_catalog"] = {
                "success": True, "error": None,
                "data": {"skipped": "No Power Platform environment selected.", "count": 0},
            }

        steps = [
            {"id": spec["id"], "module": spec["module"], "provider": spec["provider"],
             "success": results[spec["id"]]["success"], "error": results[spec["id"]]["error"],
             "skipped": bool(
                 isinstance(results[spec["id"]]["data"], dict)
                 and results[spec["id"]]["data"].get("skipped")
             )}
            for spec in TASK_GRAPH
        ]
        succeeded = sum(1 for step in steps if step["success"])
        return {
            "success": succeeded > 0,
            "generated_at": self._now(),
            "steps": steps,
            "summary": {
                "total": len(steps),
                "succeeded": succeeded,
                "failed": len(steps) - succeeded,
                "read_only": True,
            },
            "correlated": self._correlated(
                results["azure_footprint"]["data"] or {},
                results["azure_inventory"]["data"] or {},
                results["pp_environments"]["data"] or {},
                (results["pp_catalog"]["data"] or {}).get("flows", {}),
            ),
            "token_material_returned": False,
        }
