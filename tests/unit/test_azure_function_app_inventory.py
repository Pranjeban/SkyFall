from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

from skyfall_cloud.azure_resources import AzureFunctionAppInventory


class FakeStore:
    def list_profiles(self):
        return [
            {
                "profile_id": "company-qa-12345678",
                "name": "Company QA",
                "kind": "skyfall_isolated_profile",
                "config_dir": "C:/Temp/skyfall-test-profile",
                "tenant_hint": "contoso.onmicrosoft.com",
            }
        ]

    def get_profile(self, profile_id):
        return next(item for item in self.list_profiles() if item["profile_id"] == profile_id)


class FakeProfileManager:
    def __init__(self, authenticated=True, subscription_ids=None):
        self.store = FakeStore()
        self.authenticated = authenticated
        self.subscription_ids = subscription_ids or ["sub-001"]

    def get_auth_status(self, profile_id):
        return {
            "authenticated": self.authenticated,
            "profile_id": profile_id,
            "tenant_id": "tenant-001",
        }

    def list_subscriptions(self, profile_id, refresh=False):
        if not self.authenticated:
            return {"success": False, "error": "Not authenticated", "subscriptions": []}
        return {
            "success": True,
            "profile_id": profile_id,
            "profile": "Company QA",
            "subscriptions": [
                {
                    "profile": "Company QA",
                    "profile_id": profile_id,
                    "subscription_id": subscription_id,
                    "name": "QA Subscription",
                    "tenant_id": "tenant-001",
                    "state": "Enabled",
                }
                for subscription_id in self.subscription_ids
            ],
        }


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers, json):
        self.requests.append({"url": url, "headers": headers, "body": json})
        return FakeResponse(self.responses.pop(0))


class AzureFunctionAppInventoryTests(unittest.TestCase):
    def _app_payload(self):
        return {
            "data": [
                {
                    "id": "/subscriptions/sub-001/resourceGroups/rg-qa/providers/Microsoft.Web/sites/fn-qa-orders",
                    "name": "fn-qa-orders",
                    "kind": "functionapp,linux",
                    "location": "centralindia",
                    "resourceGroup": "rg-qa",
                    "subscriptionId": "sub-001",
                    "tags": {
                        "environment": "QA",
                        "owner": "platform-team",
                        "deploymentSecret": "do-not-export-this",
                        "reportNote": '=HYPERLINK("https://example.invalid","Open")',
                    },
                    "state": "Running",
                    "defaultHostName": "fn-qa-orders.azurewebsites.net",
                    "httpsOnly": True,
                    "publicNetworkAccess": "Enabled",
                    "serverFarmId": "/subscriptions/sub-001/resourceGroups/rg-qa/providers/Microsoft.Web/serverfarms/plan-qa",
                    "linuxFxVersion": "DOTNET-ISOLATED|8.0",
                    "netFrameworkVersion": "",
                    "nodeVersion": "",
                    "pythonVersion": "",
                    "powerShellVersion": "",
                    "functionsExtensionVersion": "~4",
                    "alwaysOn": True,
                    "ftpsState": "Disabled",
                    "minTlsVersion": "1.2",
                    "http20Enabled": True,
                    "functionAppScaleLimit": "20",
                    "preWarmedInstanceCount": "1",
                    "virtualNetworkSubnetId": "/subscriptions/sub-001/resourceGroups/rg-network/providers/Microsoft.Network/virtualNetworks/vnet-qa/subnets/functions",
                    "identityType": "SystemAssigned",
                }
            ],
            "resultTruncated": "false",
        }

    def _plans_payload(self):
        return {
            "data": [
                {
                    "id": "/subscriptions/sub-001/resourceGroups/rg-qa/providers/Microsoft.Web/serverfarms/plan-qa",
                    "planName": "plan-qa",
                    "planKind": "linux",
                    "planLocation": "centralindia",
                    "planSkuName": "EP1",
                    "planSkuTier": "ElasticPremium",
                    "planSkuSize": "EP1",
                    "planReserved": "true",
                    "planMaximumElasticWorkerCount": "20",
                    "planPerSiteScaling": "false",
                    "planNumberOfWorkers": "1",
                    "planWorkerSize": "1",
                }
            ],
            "resultTruncated": "false",
        }

    def test_inventory_generates_workbook_and_excludes_secret_like_tag_values(self):
        fake_client = FakeHttpClient([self._app_payload(), self._plans_payload()])
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AzureFunctionAppInventory(
                profile_manager=FakeProfileManager(),
                project_root=temp_dir,
                token_provider=lambda _profile_id: "unit-test-token",
                http_client_factory=lambda: fake_client,
            )
            result = service.inventory(profile_id="company-qa-12345678", generate_excel=True)

            self.assertTrue(result["success"])
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["function_app_count"], 1)
            self.assertEqual(result["subscription_count"], 1)
            self.assertEqual(result["preview"][0]["runtime"], "DOTNET-ISOLATED|8.0")
            self.assertFalse(result["cloud_resources_modified"])
            self.assertFalse(result["secrets_returned"])
            report_path = Path(result["report"]["path"])
            self.assertTrue(report_path.is_file())
            self.assertRegex(report_path.name, r"^Azure-Function-Apps-.*-\d{4}-\d{2}-\d{2}(?:-\d{2})?\.xlsx$")
            self.assertEqual(
                result["report"]["worksheets"],
                ["Summary", "Function Apps", "Hosting Plans", "Configuration", "Networking", "Tags", "Discovery Errors"],
            )

            workbook = load_workbook(report_path, read_only=True, data_only=True)
            self.assertIn("Function Apps", workbook.sheetnames)
            apps_sheet = workbook["Function Apps"]
            headers = [cell.value for cell in next(apps_sheet.iter_rows(min_row=1, max_row=1))]
            self.assertIn("Runtime Stack", headers)
            self.assertIn("Plan SKU", headers)
            tags_sheet = workbook["Tags"]
            tag_rows = list(tags_sheet.iter_rows(min_row=2, values_only=True))
            serialized_tags = repr(tag_rows)
            self.assertNotIn("do-not-export-this", serialized_tags)
            self.assertIn("[REDACTED]", serialized_tags)
            formula_like_values = [
                cell
                for row in tags_sheet.iter_rows(min_row=2)
                for cell in row
                if isinstance(cell.value, str) and "HYPERLINK" in cell.value
            ]
            self.assertEqual(len(formula_like_values), 1)
            self.assertTrue(formula_like_values[0].value.startswith("'=HYPERLINK"))
            self.assertNotEqual(formula_like_values[0].data_type, "f")
            workbook.close()

            self.assertEqual(len(fake_client.requests), 2)
            self.assertEqual(fake_client.requests[0]["headers"]["Authorization"], "Bearer unit-test-token")
            self.assertEqual(fake_client.requests[0]["body"]["subscriptions"], ["sub-001"])

    def test_test_mode_blocks_before_token_or_network_access(self):
        service = AzureFunctionAppInventory(
            profile_manager=FakeProfileManager(),
            token_provider=lambda _profile_id: (_ for _ in ()).throw(AssertionError("token provider must not run")),
            http_client_factory=lambda: (_ for _ in ()).throw(AssertionError("HTTP client must not be created")),
        )
        with patch.dict(os.environ, {"SKYFALL_TEST_MODE": "1"}):
            result = service.inventory()
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "blocked_test_mode")
        self.assertFalse(result["cloud_resources_modified"])

    def test_unauthenticated_profile_returns_clear_failure_without_token_request(self):
        service = AzureFunctionAppInventory(
            profile_manager=FakeProfileManager(authenticated=False),
            token_provider=lambda _profile_id: (_ for _ in ()).throw(AssertionError("token provider must not run")),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service.project_root = Path(temp_dir)
            result = service.inventory(profile_id="company-qa-12345678")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("not authenticated", result["errors"][0]["error"].casefold())

    def test_unknown_subscription_filter_is_not_queried(self):
        service = AzureFunctionAppInventory(
            profile_manager=FakeProfileManager(subscription_ids=["sub-001"]),
            token_provider=lambda _profile_id: (_ for _ in ()).throw(AssertionError("token provider must not run")),
        )
        result = service.inventory(
            profile_id="company-qa-12345678",
            subscription_ids=["sub-not-accessible"],
            generate_excel=False,
        )
        self.assertFalse(result["success"])
        self.assertIn("not enabled or not visible", result["errors"][0]["error"])

    def test_repeated_resource_graph_skip_token_is_rejected(self):
        class RepeatingClient(FakeHttpClient):
            def post(self, url, headers, json):
                self.requests.append({"url": url, "headers": headers, "body": json})
                return FakeResponse({"data": [], "$skipToken": "same-token", "resultTruncated": "true"})

        client = RepeatingClient([])
        service = AzureFunctionAppInventory(
            profile_manager=FakeProfileManager(),
            token_provider=lambda _profile_id: "unit-test-token",
            http_client_factory=lambda: client,
        )
        with self.assertRaisesRegex(Exception, "repeated pagination token"):
            service._query_resource_graph(client, "unit-test-token", ["sub-001"], "Resources | project id")


if __name__ == "__main__":
    unittest.main()
