from __future__ import annotations

import json
import unittest

from skyfall_mcp.tools.core import (
    describe_skyfall_capability,
    get_skyfall_status,
    list_skyfall_capabilities,
)


class CoreMcpToolTests(unittest.TestCase):
    def test_status_reports_read_only_microsoft_discovery_and_no_execution(self) -> None:
        payload = json.loads(get_skyfall_status())
        self.assertEqual(payload["application"], "SKYFALL")
        self.assertEqual(payload["mcp_status"], "running")
        self.assertEqual(payload["azure_connector"], "read_only_account_subscription_general_resource_and_function_app_inventory_available")
        self.assertEqual(payload["power_platform_connector"], "read_only_profile_environment_power_apps_and_cloud_flow_inventory_available")
        self.assertEqual(payload["script_execution"], "not_enabled")
        self.assertEqual(payload["cloud_resource_modification"], "not_enabled")
        self.assertEqual(payload["version"], "0.9.2")
        self.assertEqual(payload["enabled_tools"], 45)
        self.assertEqual(payload["enabled_core_tools"], 3)
        self.assertEqual(payload["enabled_workspace_tools"], 4)
        self.assertEqual(payload["enabled_azure_discovery_tools"], 4)
        self.assertEqual(payload["enabled_azure_resource_tools"], 2)
        self.assertEqual(payload["enabled_power_platform_discovery_tools"], 4)
        self.assertEqual(payload["enabled_authentication_tools"], 3)
        self.assertEqual(payload["enabled_power_platform_resource_tools"], 2)

    def test_list_capabilities_returns_only_enabled_registry_entries(self) -> None:
        payload = json.loads(list_skyfall_capabilities("core"))
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["scope"], "registered_and_enabled_only")

    def test_describe_tool_returns_capability_metadata(self) -> None:
        payload = json.loads(describe_skyfall_capability("core.get_status"))
        self.assertEqual(payload["tool_name"], "get_skyfall_status")
        self.assertEqual(payload["risk"], "read_only")

    def test_describe_unknown_tool_returns_error_without_execution(self) -> None:
        payload = json.loads(describe_skyfall_capability("filesystem.read_file"))
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
