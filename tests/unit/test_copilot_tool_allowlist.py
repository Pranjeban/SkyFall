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
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "test_mcp_server.py"


class TestCopilotToolAllowlist(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = COPILOT_SERVICE.read_text(encoding="utf-8")
        instruction_block = re.search(
            r'SKYFALL_SYSTEM_INSTRUCTIONS\s*=\s*"""([\s\S]*?)"""\.strip\(\)',
            cls.source,
        )
        if instruction_block is None:
            raise AssertionError("SKYFALL_SYSTEM_INSTRUCTIONS constant not found")
        cls.instructions = instruction_block.group(1)
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
        smoke = SMOKE_SCRIPT.read_text(encoding="utf-8")
        smoke_block = re.search(r"EXPECTED_TOOL_NAMES\s*=\s*\{([\s\S]*?)\}", smoke)
        if smoke_block is None:
            raise AssertionError("EXPECTED_TOOL_NAMES set not found in scripts/test_mcp_server.py")
        cls.smoke_names = set(re.findall(r'"([A-Za-z0-9_]+)"', smoke_block.group(1)))

    def test_allow_list_covers_every_enabled_tool(self) -> None:
        self.assertEqual(len(self.enabled), 36)
        self.assertEqual(set(self.allowed), set(self.enabled))
        self.assertEqual(len(self.allowed), len(self.enabled))

    def test_mcp_smoke_script_expects_every_enabled_tool(self) -> None:
        self.assertEqual(self.smoke_names, set(self.enabled))
        self.assertEqual(len(self.smoke_names), 36)

    def test_system_instructions_describe_the_v11_boundary(self) -> None:
        for token in (
            "route_copilot_intent",
            "build_operation_plan",
            "governance_summary",
            "find_azure_function_app",
            "which subscription is",
            "not_found_partial",
            "MSAL sessions independent",
            "never executes",
            "plan_execution",
            "get_execution_history",
            "resolve, plan and dry-run simulate only",
            "never start a process",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.instructions)

    def test_sdk_identifier_contract_is_locked_statically(self) -> None:
        """Static check: SDK 1.0.34 exposes MCP tools as mcp:<server-key>-<tool-name>."""
        for token in (
            'f"mcp:{MCP_SERVER_KEY}-{tool_name}"',
            '"available_tools": list(MCP_AVAILABLE_TOOL_IDS)',
            '"mcp_servers": self._mcp_server_configuration()',
            '"tools": list(MCP_TOOL_NAMES)',
            '"command": sys.executable',
            '"args": ["-m", "skyfall_mcp.server"]',
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.source)

    def test_system_instructions_recognize_real_chat_tool_availability(self) -> None:
        for token in (
            "Copilot + MCP connected",
            "Do not tell the user the tools are",
            "briefly name the tool in",
            "partial discovery or no match",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.instructions)

    def test_no_stale_v09_tool_wording(self) -> None:
        self.assertNotIn("SKYFALL v0.9.2 permits", self.source)
        self.assertNotIn("Twenty tools", self.source)


if __name__ == "__main__":
    unittest.main()
