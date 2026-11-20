"""Unit tests for v1.1 Module 2.2/2.3 Azure Resource Graph inventory.

ARM/Resource Graph traffic is faked: no live tenant, network or credentials.
Tests prove token-safe errors, provider isolation and query construction.
"""

from __future__ import annotations

import unittest
from typing import Any

from skyfall_cloud.azure_graph_inventory import (
    RESOURCE_GRAPH_PATH,
    AzureInventoryError,
    AzureResourceInventory,
)
from skyfall_cloud.azure_discovery import AZURE_MANAGEMENT_BASE

TOKEN = "GRAPH_SECRET_TOKEN"


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
    def __init__(self) -> None:
        self.post_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []
        self.post_response = FakeResponse(200, {
            "data": {
                "columns": [
                    {"name": "id"}, {"name": "name"}, {"name": "type"},
                    {"name": "location"}, {"name": "resourceGroup"},
                    {"name": "subscriptionId"}, {"name": "kind"},
                ],
                "rows": [
                    ["/subs/s1/vm1", "vm1", "Microsoft.Compute/virtualMachines", "uksouth", "rg1", "s1", ""],
                    ["/subs/s1/fn1", "fn1", "Microsoft.Web/sites", "uksouth", "rg1", "s1", "functionapp"],
                ],
            }
        })
        self.get_response = FakeResponse(200, {
            "id": "/subs/s1/vm1", "name": "vm1", "type": "Microsoft.Compute/virtualMachines",
            "location": "uksouth", "tags": {"env": "prod"},
            "properties": {"provisioningState": "Succeeded"},
        })

    def post(self, url, params=None, headers=None, json=None, timeout=None) -> FakeResponse:
        self.post_calls.append({
            "url": url, "params": params, "headers": headers, "json": json, "timeout": timeout
        })
        return self.post_response

    def get(self, url, params=None, headers=None, timeout=None) -> FakeResponse:
        self.get_calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return self.get_response


class TestAzureResourceInventory(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = FakeAuthority()
        self.azure = FakeProfile("azure-1")
        self.pp = FakeProfile("pp-1", "powerplatform")
        self.authority.registry.profiles = {self.azure.profile_id: self.azure, self.pp.profile_id: self.pp}
        self.http = FakeHttp()
        self.inventory = AzureResourceInventory(self.authority, http_client=self.http)

    def test_query_construction_and_token_safety(self) -> None:
        result = self.inventory.query_resources(["s1"])
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        call = self.http.post_calls[0]
        self.assertEqual(call["url"], f"{AZURE_MANAGEMENT_BASE}{RESOURCE_GRAPH_PATH}")
        self.assertEqual(call["headers"]["Authorization"], f"Bearer {TOKEN}")
        self.assertEqual(call["json"]["subscriptions"], ["s1"])
        self.assertIn("Resources", call["json"]["query"])
        self.assertNotIn(TOKEN, str(result))
        self.assertNotIn(TOKEN, str(call["json"]))

    def test_category_filter_builds_narrower_query(self) -> None:
        all_query = self.inventory.build_query()
        narrow = self.inventory.build_query(["function_apps"])
        self.assertLess(len(narrow), len(all_query))
        self.assertIn("microsoft.web/sites", narrow)
        self.assertNotIn("microsoft.storage/storageaccounts", narrow)
        with self.assertRaises(AzureInventoryError):
            self.inventory.build_query(["not_a_category"])

    def test_inventory_uses_generated_query(self) -> None:
        result = self.inventory.inventory(["s1"], categories=["virtual_machines"])
        self.assertEqual(result["count"], 2)
        self.assertIn("microsoft.compute/virtualmachines", self.http.post_calls[0]["json"]["query"])

    def test_denied_access_error_never_leaks_token(self) -> None:
        self.http.post_response = FakeResponse(403, {})
        with self.assertRaises(AzureInventoryError) as raised:
            self.inventory.query_resources(["s1"])
        self.assertNotIn(TOKEN, str(raised.exception))
        self.assertIn("permissions", str(raised.exception).lower())

    def test_powerplatform_profile_cannot_query_azure(self) -> None:
        with self.assertRaises(ValueError):
            self.inventory.query_resources(["s1"], profile_id=self.pp.profile_id)
        self.assertEqual(self.http.post_calls, [])

    def test_invalid_subscription_and_limit_rejected(self) -> None:
        with self.assertRaises(AzureInventoryError):
            self.inventory.query_resources([])
        with self.assertRaises(AzureInventoryError):
            self.inventory.query_resources(["s1"], max_results=99999)

    def test_get_resource_sanitizes_payload(self) -> None:
        result = self.inventory.get_resource("/subs/s1/vm1")
        self.assertEqual(result["name"], "vm1")
        self.assertEqual(result["properties"]["provisioningState"], "Succeeded")
        self.assertNotIn(TOKEN, str(result))
        self.assertEqual(self.http.get_calls[0]["headers"]["Authorization"], f"Bearer {TOKEN}")

    def test_get_resource_rejects_traversal(self) -> None:
        with self.assertRaises(AzureInventoryError):
            self.inventory.get_resource("/../evil")
        with self.assertRaises(AzureInventoryError):
            self.inventory.get_resource("https://evil.example")

    def test_compare_and_missing_tags(self) -> None:
        left = {"id": "a", "type": "t1", "location": "uksouth", "resourceGroup": "rg1", "kind": ""}
        right = {**left, "id": "b", "location": "westeurope"}
        self.assertFalse(self.inventory.compare_resources(left, right)["same"])
        self.assertTrue(self.inventory.compare_resources(left, left)["same"])
        missing = self.inventory.find_missing_tags(
            [{"id": "r1", "tags": {"env": "prod"}}, {"id": "r2", "tags": {}}], ["env", "owner"]
        )
        self.assertEqual([f["resource"] for f in missing], ["r1", "r2"])
        self.assertEqual(missing[1]["missing_tags"], ["env", "owner"])


if __name__ == "__main__":
    unittest.main()
