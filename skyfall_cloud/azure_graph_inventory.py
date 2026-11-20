"""Azure resource inventory via Azure Resource Graph (v1.1 Module 2.2/2.3).

Read-only, large-scale discovery of the Azure resource types required by the
v1.1 spec. Authentication comes from the unified MSAL authority; an Azure
identity profile is mandatory, so Power Platform sessions cannot be reused.

Every HTTP interaction is injected, making the module fully testable with
fakes. Bearer tokens never appear in returned data, queries or errors.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from skyfall_cloud.azure_discovery import AZURE_MANAGEMENT_BASE, AzureDiscoveryService
from skyfall_cloud.msal_identity import UnifiedIdentityAuthority

RESOURCE_GRAPH_PATH = "/providers/Microsoft.ResourceGraph/resources"
RESOURCE_GRAPH_VERSION = "2021-03-01"
_RESOURCE_ID_PATTERN = re.compile(r"^/[A-Za-z0-9._/\-]+$")

# v1.1 §2.2 resource intelligence: spec label -> ARM resource type prefix.
RESOURCE_TYPE_FILTERS: dict[str, str] = {
    "virtual_machines": "microsoft.compute/virtualmachines",
    "vm_scale_sets": "microsoft.compute/virtualmachinescalesets",
    "app_services": "microsoft.web/sites",
    "function_apps": "microsoft.web/sites",
    "storage_accounts": "microsoft.storage/storageaccounts",
    "azure_sql": "microsoft.sql/servers",
    "postgresql": "microsoft.dbforpostgresql/servers",
    "cosmos_db": "microsoft.documentdb/databaseaccounts",
    "virtual_networks": "microsoft.network/virtualnetworks",
    "subnets": "microsoft.network/virtualnetworks/subnets",
    "network_security_groups": "microsoft.network/networksecuritygroups",
    "load_balancers": "microsoft.network/loadbalancers",
    "application_gateways": "microsoft.network/applicationgateways",
    "public_ips": "microsoft.network/publicipaddresses",
    "private_endpoints": "microsoft.network/privateendpoints",
    "key_vaults": "microsoft.keyvault/vaults",
    "container_registries": "microsoft.containerregistry/registries",
    "azure_backup": "microsoft.recoveryservices/vaults",
    "monitor_resources": "microsoft.insights/components",
    "log_analytics_workspaces": "microsoft.operationalinsights/workspaces",
}

_RESULT_FIELDS = (
    "id", "name", "type", "location", "resourceGroup", "subscriptionId", "kind",
)


class AzureInventoryError(RuntimeError):
    """User-facing inventory failure that never contains credential material."""


class AzureResourceInventory:
    """Query Azure Resource Graph for a dynamically discovered inventory."""

    def __init__(
        self,
        identity: UnifiedIdentityAuthority,
        *,
        http_client: Any = None,
    ) -> None:
        self.identity = identity
        self.http = http_client or httpx
        self.discovery = AzureDiscoveryService(identity, http_client=http_client)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def build_query(categories: list[str] | None = None) -> str:
        keys = list(RESOURCE_TYPE_FILTERS if not categories else categories)
        if not keys:
            raise AzureInventoryError("Select at least one resource category.")
        unknown = [key for key in keys if key not in RESOURCE_TYPE_FILTERS]
        if unknown:
            raise AzureInventoryError(f"Unsupported resource categories: {', '.join(unknown)}")
        types = sorted({RESOURCE_TYPE_FILTERS[key] for key in keys})
        type_list = ", ".join(f"'{item}'" for item in types)
        return (
            "Resources\n"
            f"| where type in~ ({type_list})\n"
            "| project id, name, type, location, resourceGroup, subscriptionId, kind, tags\n"
            "| order by type asc, name asc"
        )

    def _token_for(self, profile_id: str | None) -> str:
        profile = self.discovery._require_azure_profile(profile_id)
        return self.identity.acquire_token(profile.profile_id)

    @staticmethod
    def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise AzureInventoryError("Azure Resource Graph returned an unexpected response.")
        data = payload["data"]
        columns = data.get("columns")
        rows = data.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            raise AzureInventoryError("Azure Resource Graph returned an unexpected response.")
        names = [
            str(column.get("name"))
            for column in columns
            if isinstance(column, dict) and column.get("name")
        ]
        return [
            {key: value for key, value in zip(names, row) if key}
            for row in rows
            if isinstance(row, list)
        ]

    # -- public inventory --------------------------------------------------

    def query_resources(
        self,
        subscription_ids: list[str],
        *,
        query: str | None = None,
        profile_id: str | None = None,
        max_results: int = 1000,
    ) -> dict[str, Any]:
        """Run a caller-supplied or generated Kusto query across subscriptions."""
        if not isinstance(subscription_ids, list) or not subscription_ids:
            raise AzureInventoryError("Select at least one Azure subscription.")
        if any(not isinstance(sub, str) or not sub.strip() for sub in subscription_ids):
            raise AzureInventoryError("Subscription identifiers must be non-empty strings.")
        if not isinstance(max_results, int) or not 1 <= max_results <= 5000:
            raise AzureInventoryError("Result limit must be between 1 and 5000.")
        kusto = query or self.build_query()
        if not isinstance(kusto, str) or not kusto.strip() or len(kusto) > 10000:
            raise AzureInventoryError("The resource query is invalid.")
        token = self._token_for(profile_id)
        url = f"{AZURE_MANAGEMENT_BASE}{RESOURCE_GRAPH_PATH}"
        try:
            response = self.http.post(
                url,
                params={"api-version": RESOURCE_GRAPH_VERSION},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "query": kusto,
                    "subscriptions": list(subscription_ids),
                    "options": {"$top": max_results},
                },
                timeout=60,
            )
        except Exception as exc:
            raise AzureInventoryError("Azure Resource Graph could not be reached.") from exc
        status = int(getattr(response, "status_code", 0) or 0)
        if status in (401, 403):
            raise AzureInventoryError(
                "Microsoft denied Resource Graph access. Check Azure permissions and tenant consent."
            )
        if status >= 400:
            raise AzureInventoryError(f"Azure Resource Graph returned HTTP {status}.")
        try:
            rows = self._rows_from_payload(response.json())
        except ValueError as exc:
            raise AzureInventoryError("Azure Resource Graph returned an unexpected response.") from exc
        resources = [
            {field: str(row[field]) for field in _RESULT_FIELDS if field in row and row[field] is not None}
            for row in rows
        ][:max_results]
        return {
            "success": True,
            "resources": resources,
            "count": len(resources),
            "truncated": len(rows) > max_results,
            "discovery_method": "azure_resource_graph",
        }

    def inventory(
        self,
        subscription_ids: list[str],
        *,
        categories: list[str] | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        """Inventory the spec-defined resource categories across subscriptions."""
        return self.query_resources(
            subscription_ids, query=self.build_query(categories), profile_id=profile_id
        )

    def get_resource(self, resource_id: str, *, profile_id: str | None = None) -> dict[str, Any]:
        """Read one resource's ARM properties (read-only configuration inspect)."""
        value = (resource_id or "").strip()
        if (
            not _RESOURCE_ID_PATTERN.fullmatch(value)
            or len(value) > 2048
            or ".." in value
            or "//" in value
        ):
            raise AzureInventoryError("Invalid Azure resource identifier.")
        token = self._token_for(profile_id)
        url = f"{AZURE_MANAGEMENT_BASE}{value}"
        try:
            response = self.http.get(
                url,
                params={"api-version": "2021-04-01"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
        except Exception as exc:
            raise AzureInventoryError("Azure resource configuration could not be read.") from exc
        status = int(getattr(response, "status_code", 0) or 0)
        if status in (401, 403):
            raise AzureInventoryError("Microsoft denied access to this resource. Check permissions.")
        if status >= 400:
            raise AzureInventoryError(f"Azure returned HTTP {status} for this resource.")
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise AzureInventoryError("Azure returned an unexpected resource response.") from exc
        if not isinstance(payload, dict):
            raise AzureInventoryError("Azure returned an unexpected resource response.")
        properties = payload.get("properties")
        return {
            "id": str(payload.get("id") or value),
            "name": str(payload.get("name") or ""),
            "type": str(payload.get("type") or ""),
            "location": str(payload.get("location") or ""),
            "tags": payload.get("tags") if isinstance(payload.get("tags"), dict) else {},
            "properties": properties if isinstance(properties, dict) else {},
        }

    @staticmethod
    def compare_resources(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        """Compare two inventory records for configuration-drift reporting."""
        fields = ("type", "location", "resourceGroup", "kind")
        differences = [
            {"field": field, "left": left.get(field), "right": right.get(field)}
            for field in fields
            if left.get(field) != right.get(field)
        ]
        return {
            "left": left.get("id"),
            "right": right.get("id"),
            "same": not differences,
            "differences": differences,
        }

    @staticmethod
    def find_missing_tags(resources: list[dict[str, Any]], required: list[str]) -> list[dict[str, Any]]:
        """Identify resources missing one or more required tags (spec §2.3/2.6)."""
        if not required:
            return []
        findings: list[dict[str, Any]] = []
        for resource in resources:
            tags = resource.get("tags") if isinstance(resource.get("tags"), dict) else {}
            missing = [tag for tag in required if tag not in tags]
            if missing:
                findings.append({"resource": resource.get("id"), "missing_tags": missing})
        return findings
