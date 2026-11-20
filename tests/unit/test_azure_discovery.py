"""Unit tests for v1.1 Module 2.1 Azure tenant/subscription discovery.

All ARM traffic is faked: no live tenant, network, credentials or GUI. Tests
assert that bearer tokens never appear in results, errors or logged calls.
"""

from __future__ import annotations

import unittest
from typing import Any

from skyfall_cloud.azure_discovery import AzureDiscoveryService, AZURE_MANAGEMENT_BASE


TOKEN = "SUPER_SECRET_BEARER_TOKEN"


class FakeProfile:
    def __init__(self, profile_id: str, provider: str = "azure") -> None:
        self.profile_id = profile_id
        self.provider = provider


class FakeRegistry:
    def __init__(self) -> None:
        self.profiles: dict[str, FakeProfile] = {}

    def get_profile(self, profile_id: str | None) -> FakeProfile | None:
        if profile_id is None:
            return next(iter(self.profiles.values()), None)
        return self.profiles.get(profile_id)


class FakeAuthority:
    def __init__(self) -> None:
        self.registry = FakeRegistry()

    def acquire_token(self, profile_id: str, scopes: list[str] | None = None) -> str:
        return TOKEN


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeHttp:
    def __init__(self, routes: dict[str, FakeResponse]) -> None:
        self.routes = routes
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params=None, headers=None, timeout=None) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return self.routes.get(url, FakeResponse(200, {"value": []}))


class TestAzureDiscoveryService(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = FakeAuthority()
        self.azure = FakeProfile("azure-1")
        self.pp = FakeProfile("pp-1", "powerplatform")
        self.authority.registry.profiles = {self.azure.profile_id: self.azure, self.pp.profile_id: self.pp}
        self.routes: dict[str, FakeResponse] = {
            f"{AZURE_MANAGEMENT_BASE}/tenants": FakeResponse(200, {"value": [
                {"tenantId": "t-1", "displayName": "Contoso", "countryCode": "GB"},
                {"tenantId": "t-1", "displayName": "Contoso duplicate"},
                {"displayName": "no id"},
            ]}),
            f"{AZURE_MANAGEMENT_BASE}/subscriptions": FakeResponse(200, {"value": [
                {"subscriptionId": "s-1", "displayName": "Prod", "state": "Enabled", "tenantId": "t-1", "id": "/subs/s-1"},
                {"subscriptionId": "s-2", "displayName": "Dev", "state": "Disabled", "tenantId": "t-1", "id": "/subs/s-2"},
            ]}),
            f"{AZURE_MANAGEMENT_BASE}/providers/Microsoft.Management/managementGroups": FakeResponse(200, {"value": [
                {"name": "mg-1", "id": "/mg/mg-1", "properties": {"displayName": "Root"}},
            ]}),
        }
        self.http = FakeHttp(self.routes)
        self.service = AzureDiscoveryService(self.authority, http_client=self.http)

    def test_tenant_discovery_dedups_and_hides_token(self) -> None:
        result = self.service.list_tenants()
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["tenants"][0]["tenant_id"], "t-1")
        self.assertNotIn(TOKEN, str(result))
        self.assertEqual(self.http.calls[0]["headers"]["Authorization"], f"Bearer {TOKEN}")

    def test_subscription_discovery_and_enabled_count(self) -> None:
        result = self.service.list_subscriptions()
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["enabled"], 1)
        self.assertEqual(result["subscriptions"][0]["display_name"], "Prod")
        self.assertNotIn(TOKEN, str(result))

    def test_management_group_discovery(self) -> None:
        result = self.service.list_management_groups()
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["management_groups"][0]["display_name"], "Root")

    def test_denied_access_error_never_leaks_token(self) -> None:
        self.routes[f"{AZURE_MANAGEMENT_BASE}/subscriptions"] = FakeResponse(403, {"error": "denied"})
        result = self.service.list_subscriptions()
        self.assertFalse(result["success"])
        self.assertNotIn(TOKEN, str(result))
        self.assertIn("permissions", result["error"].lower())

    def test_powerplatform_profile_cannot_drive_azure_discovery(self) -> None:
        with self.assertRaises(ValueError):
            self.service.list_tenants(self.pp.profile_id)
        self.assertEqual(self.http.calls, [])

    def test_missing_profile_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.service.list_subscriptions("does-not-exist")

    def test_overview_survives_partial_failure(self) -> None:
        self.routes[f"{AZURE_MANAGEMENT_BASE}/tenants"] = FakeResponse(500, {})
        result = self.service.tenant_subscription_overview()
        self.assertFalse(result["tenants"]["success"])
        self.assertTrue(result["subscriptions"]["success"])
        self.assertEqual(result["management_groups"]["count"], 1)
        self.assertTrue(result["sessions_independent"])
        self.assertNotIn(TOKEN, str(result))

    def test_subscription_comparison(self) -> None:
        left = {"subscription_id": "s-1", "display_name": "Prod", "state": "Enabled", "tenant_id": "t-1"}
        right = {"subscription_id": "s-2", "display_name": "Prod", "state": "Disabled", "tenant_id": "t-2"}
        result = self.service.compare_subscriptions(left, right)
        self.assertFalse(result["same"])
        self.assertEqual({d["field"] for d in result["differences"]}, {"state", "tenant_id"})
        self.assertTrue(self.service.compare_subscriptions(left, left)["same"])


if __name__ == "__main__":
    unittest.main()
