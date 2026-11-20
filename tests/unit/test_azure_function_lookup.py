"""Contract tests for the read-only Function App name lookup MCP tool."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from skyfall_mcp.tools.azure_resources import find_azure_function_app

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestAzureFunctionLookupTool(unittest.TestCase):
    def test_tool_delegates_with_lookup_arguments(self) -> None:
        expected = {
            "success": True,
            "status": "success",
            "match_count": 1,
            "matches": [{"name": "fn-qa-orders", "subscription_name": "QA Subscription"}],
            "summary": "Found 1 match for 'fn-qa-orders'.",
            "cloud_resources_modified": False,
            "secrets_returned": False,
        }
        with patch("skyfall_mcp.tools.azure_resources.AzureFunctionAppInventory") as factory:
            factory.return_value.find_function_apps_by_name.return_value = expected
            payload = json.loads(
                find_azure_function_app(
                    "fn-qa-orders",
                    profile_id="profile-1",
                    subscription_ids=["sub-001"],
                    exact=False,
                    max_results=5,
                )
            )
            factory.return_value.find_function_apps_by_name.assert_called_once_with(
                name="fn-qa-orders",
                profile_id="profile-1",
                subscription_ids=["sub-001"],
                exact=False,
                max_results=5,
            )

        self.assertEqual(payload, expected)
        self.assertEqual(payload["summary"], "Found 1 match for 'fn-qa-orders'.")

    def test_invalid_request_is_token_safe(self) -> None:
        with patch("skyfall_mcp.tools.azure_resources.AzureFunctionAppInventory") as factory:
            factory.return_value.find_function_apps_by_name.side_effect = ValueError(
                "Function App name must be 1-200 visible characters."
            )
            payload = json.loads(find_azure_function_app("   "))

        self.assertFalse(payload["success"])
        self.assertEqual(payload["status"], "invalid_request")
        self.assertIn("1-200 visible characters", payload["error"])
        self.assertFalse(payload["cloud_resources_modified"])
        self.assertFalse(payload["secrets_returned"])

    def test_runtime_exception_is_redacted_to_type_and_short_text(self) -> None:
        secret = "Bearer JWT-SECRET-VALUE"
        with patch("skyfall_mcp.tools.azure_resources.AzureFunctionAppInventory") as factory:
            factory.return_value.find_function_apps_by_name.side_effect = RuntimeError(secret)
            payload = json.loads(find_azure_function_app("fn-qa-orders"))

        self.assertEqual(payload["status"], "failed")
        self.assertIn("RuntimeError", payload["error"])
        self.assertNotIn("JWT-SECRET-VALUE", json.dumps(payload))
        self.assertFalse(payload["secrets_returned"])

    def test_wiring_includes_lookup_in_server_catalogue_and_worker(self) -> None:
        server = (REPO_ROOT / "skyfall_mcp" / "server.py").read_text(encoding="utf-8")
        worker = (REPO_ROOT / "skyfall_cloud" / "worker.py").read_text(encoding="utf-8")
        main_window = (REPO_ROOT / "app" / "desktop" / "main_window.py").read_text(encoding="utf-8")
        for text, token in (
            (server, "def find_azure_function_app("),
            (worker, "azure_function_app_lookup"),
            (main_window, "azure_function_app_lookup"),
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
