"""Azure tenant, subscription and management-group discovery (v1.1 Module 2.1).

Read-only discovery through the official Azure Resource Manager REST API,
authenticated by the unified MSAL identity authority (Module 4). An Azure
identity profile is REQUIRED: Power Platform profiles cannot be used here,
which enforces the v1.1 rule that the two providers' sessions are independent.

No token, header or raw response body is ever placed in a result or error.
The HTTP client is dependency-injected so discovery is unit-testable with
fakes (no tenant, network or credentials required).
"""

from __future__ import annotations

from typing import Any

import httpx

from skyfall_cloud.msal_identity import AZURE_SCOPE, UnifiedIdentityAuthority

AZURE_MANAGEMENT_BASE = "https://management.azure.com"

_ENDPOINTS = {
    "tenants": ("/tenants", "2020-01-01"),
    "subscriptions": ("/subscriptions", "2021-01-01"),
    "management_groups": (
        "/providers/Microsoft.Management/managementGroups",
        "2020-05-01",
    ),
}


class AzureDiscoveryError(RuntimeError):
    """A user-facing discovery failure that never contains credential material."""


class AzureDiscoveryService:
    """Read-only ARM discovery bound to an Azure MSAL identity profile."""

    def __init__(
        self,
        identity: UnifiedIdentityAuthority,
        *,
        http_client: Any = None,
        scopes: list[str] | None = None,
    ) -> None:
        self.identity = identity
        self.http = http_client or httpx
        self.scopes = scopes or [AZURE_SCOPE]

    # -- internals ---------------------------------------------------------

    def _require_azure_profile(self, profile_id: str | None) -> Any:
        profile = self.identity.registry.get_profile(profile_id)
        if profile is None:
            raise KeyError("Select an Azure identity profile before discovering Azure resources.")
        if profile.provider != "azure":
            raise ValueError(
                "This identity profile is for Power Platform. Azure discovery requires a separate Azure sign-in."
            )
        return profile

    def _collection(self, profile_id: str, endpoint: str) -> list[dict[str, Any]]:
        path, version = _ENDPOINTS[endpoint]
        profile = self._require_azure_profile(profile_id)
        token = self.identity.acquire_token(profile.profile_id, scopes=self.scopes)
        url = f"{AZURE_MANAGEMENT_BASE}{path}"
        try:
            response = self.http.get(
                url,
                params={"api-version": version},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
        except Exception as exc:
            raise AzureDiscoveryError("Azure discovery could not reach the management API.") from exc
        status = int(getattr(response, "status_code", 0) or 0)
        if status in (401, 403):
            raise AzureDiscoveryError(
                "Microsoft denied access. Check this profile's Azure permissions and tenant consent."
            )
        if status >= 400:
            raise AzureDiscoveryError(f"Azure management API returned HTTP {status}.")
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise AzureDiscoveryError("Azure returned an unexpected discovery response.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise AzureDiscoveryError("Azure returned an unexpected discovery response.")
        return [item for item in payload["value"] if isinstance(item, dict)]

    # -- public discovery --------------------------------------------------

    def list_tenants(self, profile_id: str | None = None) -> dict[str, Any]:
        profile = self._require_azure_profile(profile_id)
        try:
            rows = self._collection(profile.profile_id, "tenants")
        except (AzureDiscoveryError, RuntimeError, KeyError) as exc:
            return {
                "success": False,
                "error": str(exc),
                "discovery_method": "azure_resource_manager",
                "tenants": [],
                "count": 0,
            }
        tenants: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in rows:
            tenant_id = str(item.get("tenantId") or "").strip()
            if not tenant_id or tenant_id in seen:
                continue
            seen.add(tenant_id)
            tenants.append({
                "tenant_id": tenant_id,
                "display_name": str(item.get("displayName") or ""),
                "country_code": str(item.get("countryCode") or ""),
                "profile_id": profile.profile_id,
            })
        return {
            "success": True,
            "discovery_method": "azure_resource_manager",
            "tenants": tenants,
            "count": len(tenants),
        }

    def list_subscriptions(self, profile_id: str | None = None) -> dict[str, Any]:
        profile = self._require_azure_profile(profile_id)
        try:
            rows = self._collection(profile.profile_id, "subscriptions")
        except (AzureDiscoveryError, RuntimeError, KeyError) as exc:
            return {"success": False, "error": str(exc), "subscriptions": [], "count": 0}
        subscriptions: list[dict[str, Any]] = []
        for item in rows:
            subscription_id = str(item.get("subscriptionId") or "").strip()
            if not subscription_id:
                continue
            subscriptions.append({
                "subscription_id": subscription_id,
                "display_name": str(item.get("displayName") or ""),
                "state": str(item.get("state") or ""),
                "tenant_id": str(item.get("tenantId") or ""),
                "id": str(item.get("id") or ""),
                "profile_id": profile.profile_id,
            })
        return {
            "success": True,
            "subscriptions": subscriptions,
            "count": len(subscriptions),
            "enabled": sum(1 for s in subscriptions if s["state"].casefold() == "enabled"),
        }

    def list_management_groups(self, profile_id: str | None = None) -> dict[str, Any]:
        profile = self._require_azure_profile(profile_id)
        try:
            rows = self._collection(profile.profile_id, "management_groups")
        except (AzureDiscoveryError, RuntimeError, KeyError) as exc:
            return {"success": False, "error": str(exc), "management_groups": [], "count": 0}
        groups: list[dict[str, Any]] = []
        for item in rows:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
            groups.append({
                "name": name,
                "display_name": str(properties.get("displayName") or ""),
                "id": str(item.get("id") or ""),
                "profile_id": profile.profile_id,
            })
        return {
            "success": True,
            "management_groups": groups,
            "count": len(groups),
        }

    def tenant_subscription_overview(self, profile_id: str | None = None) -> dict[str, Any]:
        """Combined view; one failed call does not discard the others."""
        profile = self._require_azure_profile(profile_id)
        tenants = self.list_tenants(profile.profile_id)
        subscriptions = self.list_subscriptions(profile.profile_id)
        groups = self.list_management_groups(profile.profile_id)
        return {
            "profile_id": profile.profile_id,
            "tenants": tenants,
            "subscriptions": subscriptions,
            "management_groups": groups,
            "sessions_independent": True,
        }

    @staticmethod
    def compare_subscriptions(
        left: dict[str, Any], right: dict[str, Any]
    ) -> dict[str, Any]:
        """Compare two subscription records from ``list_subscriptions``."""
        fields = ("display_name", "state", "tenant_id")
        differences = [
            {"field": field, "left": left.get(field), "right": right.get(field)}
            for field in fields
            if left.get(field) != right.get(field)
        ]
        return {
            "left": left.get("subscription_id"),
            "right": right.get("subscription_id"),
            "same": not differences,
            "differences": differences,
        }
