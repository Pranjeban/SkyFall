from __future__ import annotations

import json
import unittest

from skyfall_mcp.tools.core import (
    describe_skyfall_capability,
    get_skyfall_status,
    list_skyfall_capabilities,
)


class CoreMcpToolTests(unittest.TestCase):
    def test_status_reports_no_external_connectors_or_execution(self) -> None:
        payload = json.loads(get_skyfall_status())
        self.assertEqual(payload["application"], "SKYFALL")
        self.assertEqual(payload["mcp_status"], "running")
        self.assertEqual(payload["azure_connector"], "not_connected")
        self.assertEqual(payload["power_platform_connector"], "not_connected")
        self.assertEqual(payload["script_execution"], "not_enabled")
        self.assertEqual(payload["enabled_tools"], 7)
        self.assertEqual(payload["enabled_core_tools"], 3)
        self.assertEqual(payload["enabled_workspace_tools"], 4)

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
