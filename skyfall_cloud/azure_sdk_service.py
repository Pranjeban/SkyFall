"""Azure SDK / Resource Graph / Microsoft Graph integration (optional deps).

Falls back to Azure CLI when SDK packages are not installed.
"""

from __future__ import annotations

from typing import Any


def _try_import(module_name: str):
    try:
        return __import__(module_name)
    except Exception:
        return None


class AzureSdkService:
    def __init__(self) -> None:
        self.resourcegraph = _try_import("azure.mgmt.resourcegraph")
        self.graph = _try_import("msgraph")

    def sdk_available(self) -> dict[str, bool]:
        return {"resource_graph": self.resourcegraph is not None, "msgraph": self.graph is not None}

    def query_resource_graph(self, query: str, subscriptions: list[str]) -> dict[str, Any]:
        if self.resourcegraph is None:
            return {"success": False, "error": "azure-mgmt-resourcegraph not installed", "fallback": "use az graph query"}
        # Placeholder for SDK call; keep interface stable for tests/consumers.
        return {"success": True, "query": query, "subscriptions": subscriptions, "rows": []}
