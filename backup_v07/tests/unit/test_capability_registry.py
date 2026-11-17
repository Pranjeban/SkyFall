from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skyfall_mcp.registry import CapabilityRegistry


class CapabilityRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CapabilityRegistry.default()

    def test_catalogue_contains_seven_enabled_tools(self) -> None:
        capabilities = self.registry.list()
        self.assertEqual(len(capabilities), 7)
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
            },
        )

    def test_every_enabled_tool_is_read_only_and_not_approval_gated(self) -> None:
        for capability in self.registry.list():
            self.assertEqual(capability.risk, "read_only")
            self.assertFalse(capability.requires_approval)
            self.assertTrue(capability.execution_enabled)

    def test_exact_capability_lookup(self) -> None:
        capability = self.registry.get("core.get_status")
        self.assertEqual(capability.tool_name, "get_skyfall_status")

    def test_unknown_capability_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            self.registry.get("azure.execute_script")

    def test_category_filter(self) -> None:
        self.assertEqual(len(self.registry.list(category="core")), 3)
        self.assertEqual(len(self.registry.list(category="workspace")), 4)
        self.assertEqual(self.registry.list(category="azure"), [])

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
