from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skyfall_mcp.registry import CapabilityRegistry


class CapabilityRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CapabilityRegistry.default()

    def test_catalogue_contains_nineteen_enabled_tools(self) -> None:
        capabilities = self.registry.list()
        self.assertEqual(len(capabilities), 19)
        self.assertEqual(
            {item.tool_name for item in capabilities},
            {
                "get_skyfall_status",
                "list_skyfall_capabilities",
                "describe_skyfall_capability",
                "get_workspace_index_status",
                "list_workspaces",
                "search_workspace_files",
                "describe_workspace_file",
                "list_azure_profiles",
                "get_azure_auth_status",
                "list_azure_subscriptions",
                "list_azure_tenants",
                "list_powerplatform_auth_profiles",
                "get_powerplatform_auth_status",
                "list_powerplatform_environments",
                "start_azure_login",
                "start_powerplatform_login",
                "get_microsoft_auth_job_status",
                "inventory_azure_function_apps",
                "inventory_power_automate_flows",
            },
        )

    def test_enabled_tools_have_expected_risk_and_are_allowlisted(self) -> None:
        for capability in self.registry.list():
            expected_risk = (
                "interactive_authentication"
                if capability.tool_name in {"start_azure_login", "start_powerplatform_login"}
                else "read_only"
            )
            self.assertEqual(capability.risk, expected_risk)
            expected_approval = capability.tool_name == "start_powerplatform_login"
            self.assertEqual(capability.requires_approval, expected_approval)
            self.assertTrue(capability.execution_enabled)
        self.assertEqual(len(self.registry.list(category="authentication")), 3)

    def test_powerplatform_login_schema_requires_explicit_side_effect_confirmation(self) -> None:
        capability = self.registry.get("powerplatform.start_login")
        confirmation = capability.input_schema["properties"]["confirm_global_profile_activation"]
        self.assertEqual(confirmation["type"], "boolean")
        self.assertFalse(confirmation["default"])
        self.assertIn("explicitly confirms", confirmation["description"])

    def test_exact_capability_lookup(self) -> None:
        capability = self.registry.get("core.get_status")
        self.assertEqual(capability.tool_name, "get_skyfall_status")

    def test_unknown_capability_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            self.registry.get("azure.execute_script")

    def test_category_filter(self) -> None:
        self.assertEqual(len(self.registry.list(category="core")), 3)
        self.assertEqual(len(self.registry.list(category="workspace")), 4)
        self.assertEqual(len(self.registry.list(category="azure")), 4)
        self.assertEqual(len(self.registry.list(category="azure_resources")), 1)
        self.assertEqual(len(self.registry.list(category="power_platform")), 3)
        self.assertEqual(len(self.registry.list(category="power_platform_resources")), 1)

    def test_duplicate_ids_are_rejected(self) -> None:
        original = json.loads(
            self.registry.catalogue_path.read_text(encoding="utf-8")
        )
        original["capabilities"].append(dict(original["capabilities"][0]))
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "capabilities.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate capability ID"):
                CapabilityRegistry(path)


if __name__ == "__main__":
    unittest.main()
