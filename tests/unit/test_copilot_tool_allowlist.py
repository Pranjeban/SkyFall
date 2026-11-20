"""Static contract: the Copilot SDK allow-list matches the enabled MCP catalogue.

This suite reads source/config as text only. It never imports PySide6, starts a
GUI, launches the Copilot runtime or contacts any network service.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COPILOT_SERVICE = REPO_ROOT / "integrations" / "copilot" / "copilot_service.py"
CAPABILITIES_JSON = REPO_ROOT / "configuration" / "capabilities.json"


class TestCopilotToolAllowlist(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = COPILOT_SERVICE.read_text(encoding="utf-8")
        catalogue = json.loads(CAPABILITIES_JSON.read_text(encoding="utf-8"))
        cls.enabled = [
            item["tool_name"]
            for item in catalogue["capabilities"]
            if item["status"] == "enabled" and item["execution_enabled"]
        ]
        block = re.search(r"MCP_TOOL_NAMES\s*=\s*\(([\s\S]*?)\)", cls.source)
        if block is None:
            raise AssertionError("MCP_TOOL_NAMES tuple not found in copilot_service.py")
        cls.allowed = re.findall(r'"([A-Za-z0-9_]+)"', block.group(1))

    def test_allow_list_covers_every_enabled_tool(self) -> None:
        self.assertEqual(len(self.enabled), 33)
        self.assertEqual(set(self.allowed), set(self.enabled))
        self.assertEqual(len(self.allowed), len(self.enabled))

    def test_system_instructions_describe_the_v11_boundary(self) -> None:
        for token in (
            "route_copilot_intent",
            "build_operation_plan",
            "governance_summary",
            "MSAL sessions independent",
            "never executes",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.source)

    def test_no_stale_v09_tool_wording(self) -> None:
        self.assertNotIn("SKYFALL v0.9.2 permits", self.source)
        self.assertNotIn("Twenty tools", self.source)


if __name__ == "__main__":
    unittest.main()
