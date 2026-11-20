"""Phase 7 backend acceptance tests (spec §10 Phase 7, lines 789-805).

Static source/contract checks only. This suite never imports ``main``, spawns
the MCP server, launches the GUI, opens the network or writes to the database.

Exit criterion context: "Backend acceptance tests pass and existing behavior
remains compatible."
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import unittest
from pathlib import Path

from memory.conversation_store import ConversationStore
from skyfall_cloud.command_runner import redact_sensitive_text
from skyfall_workspace.analyzer import detect_sensitive_content


REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_PY = REPO_ROOT / "main.py"
MAIN_WINDOW_PY = REPO_ROOT / "app" / "desktop" / "main_window.py"
CAPABILITIES_JSON = REPO_ROOT / "configuration" / "capabilities.json"
MCP_SERVER_PY = REPO_ROOT / "skyfall_mcp" / "server.py"
COMMAND_RUNNER_PY = REPO_ROOT / "skyfall_cloud" / "command_runner.py"

EXPECTED_CAPABILITY_COUNT = 33

UNWIRED_CLOUD_SERVICE_MODULES = (
    "skyfall_cloud.identity_service",
    "skyfall_cloud.command_runner",
    "skyfall_cloud.azure_sdk_service",
    "skyfall_cloud.cross_platform_service",
    "skyfall_cloud.monitoring_service",
    "skyfall_cloud.operations_service",
    "skyfall_cloud.reporting_service",
    "skyfall_cloud.audit_service",
)

CONVERSATION_STORE_NO_CALLER_METHODS = (
    "update_conversation_title",
    "delete_message",
    "search_conversations",
    "export_conversation_markdown",
    "backup_database",
)


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _mcp_tool_names(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "tool"
                ):
                    names.append(node.name)
                    break
    return names


class BackendAcceptanceActivePathTests(unittest.TestCase):
    """Active runtime wiring is verified by source scan only (no GUI import)."""

    def setUp(self) -> None:
        self.main_source = _read_source(MAIN_PY)
        self.main_window_source = _read_source(MAIN_WINDOW_PY)
        self.active_source = self.main_source + "\n" + self.main_window_source

    def test_active_path_references_core_services(self) -> None:
        for token in ("ConversationStore", "WorkspaceManager", "CapabilityRegistry", "CopilotWorker"):
            with self.subTest(token=token):
                self.assertIn(token, self.active_source)

    def test_main_window_instantiates_wired_services(self) -> None:
        self.assertIn("self.conversation_store = ConversationStore()", self.main_window_source)
        self.assertIn("self.workspace_manager = WorkspaceManager()", self.main_window_source)
        self.assertIn("self.copilot_worker = CopilotWorker(", self.main_window_source)
        self.assertIn("CapabilityRegistry.default()", self.main_window_source)

    def test_main_entry_point_loads_desktop_main_window(self) -> None:
        self.assertIn("MainWindow", self.main_source)
        self.assertIn("app.desktop.main_window", self.main_source)
        self.assertIn("def main", self.main_source)


class BackendAcceptanceMcpParityTests(unittest.TestCase):
    """Capability catalogue and MCP server tool surface must stay in parity."""

    def setUp(self) -> None:
        self.catalogue = json.loads(CAPABILITIES_JSON.read_text(encoding="utf-8"))
        self.entries = self.catalogue.get("capabilities", [])
        self.server_source = _read_source(MCP_SERVER_PY)

    def test_capability_catalogue_declares_all_enabled_capabilities(self) -> None:
        self.assertEqual(len(self.entries), EXPECTED_CAPABILITY_COUNT)
        capability_ids = [str(entry["id"]) for entry in self.entries]
        self.assertEqual(len(set(capability_ids)), EXPECTED_CAPABILITY_COUNT)
        tool_names = [str(entry["tool_name"]) for entry in self.entries]
        self.assertEqual(len(set(tool_names)), EXPECTED_CAPABILITY_COUNT)
        for entry in self.entries:
            with self.subTest(capability_id=entry["id"]):
                self.assertEqual(entry.get("status"), "enabled")
                self.assertTrue(entry.get("execution_enabled"))

    def test_mcp_server_registers_catalogue_tools(self) -> None:
        tool_names = _mcp_tool_names(self.server_source)
        self.assertEqual(len(tool_names), EXPECTED_CAPABILITY_COUNT)
        declared_tool_names = {str(entry["tool_name"]) for entry in self.entries}
        self.assertEqual(set(tool_names), declared_tool_names)


class BackendAcceptancePriorFixContractTests(unittest.TestCase):
    """Phase 7 redaction and sensitive-content detection contracts."""

    def test_redaction_covers_expected_secret_patterns(self) -> None:
        self.assertIn("api_?key", _read_source(COMMAND_RUNNER_PY))
        self.assertIn("connection_?string", _read_source(COMMAND_RUNNER_PY))
        self.assertIn("subscription_?key", _read_source(COMMAND_RUNNER_PY))

        api_key_result = redact_sensitive_text("api_key=supersecretvalue1234567890abcdef")
        self.assertNotIn("supersecretvalue1234567890abcdef", api_key_result)
        self.assertIn("[REDACTED]", api_key_result)

        connection_result = redact_sensitive_text("connection_string: Host=tcp:sqldb.host Password=SuperSecretValue1234567890")
        self.assertNotIn("SuperSecretValue1234567890", connection_result)
        self.assertIn("[REDACTED]", connection_result)

        subscription_result = redact_sensitive_text("subscription_key = C2VjcmV0a2V5c2VjcmV0a2V5abcdef123456")
        self.assertNotIn("C2VjcmV0a2V5c2VjcmV0a2V5abcdef123456", subscription_result)
        self.assertIn("[REDACTED]", subscription_result)

        bearer_result = redact_sensitive_text(
            "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        )
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", bearer_result)
        self.assertIn("Bearer [REDACTED]", bearer_result)

    def test_sensitive_content_detection_flags_high_entropy_secret(self) -> None:
        high_entropy_secret = "c3VjcmV0LWtleS1mb3ItdGhpcmQgdXNlcm5hbW9uLXRlc3Q"
        self.assertTrue(detect_sensitive_content(high_entropy_secret))
        self.assertFalse(detect_sensitive_content("def ordinary_function(param): return param + 1"))


class BackendAcceptanceUnwiredServiceTests(unittest.TestCase):
    """Tier-3 skyfall_cloud services stay present and importable (D9: preserve)."""

    def test_unwired_cloud_services_remain_present_and_importable(self) -> None:
        for module_name in UNWIRED_CLOUD_SERVICE_MODULES:
            with self.subTest(module=module_name):
                spec = importlib.util.find_spec(module_name)
                self.assertIsNotNone(spec, f"Missing skyfall_cloud module: {module_name}")
                module = importlib.import_module(module_name)
                self.assertIsNotNone(module)


class BackendAcceptanceConversationStoreContractTests(unittest.TestCase):
    """No-caller ConversationStore methods must remain present as attributes."""

    def test_no_caller_conversation_store_methods_exist(self) -> None:
        for method_name in CONVERSATION_STORE_NO_CALLER_METHODS:
            with self.subTest(method=method_name):
                self.assertTrue(hasattr(ConversationStore, method_name))


class BackendAcceptanceDormantApiTests(unittest.TestCase):
    """The dormant backend FastAPI skeleton must not enter the active runtime path."""

    def test_active_sources_do_not_import_backend_api(self) -> None:
        scanned = [MAIN_PY, MAIN_WINDOW_PY] + sorted((REPO_ROOT / "app").rglob("*.py"))
        for path in scanned:
            with self.subTest(path=str(path)):
                source = _read_source(path)
                self.assertNotIn("backend.api", source)
                self.assertNotIn("from backend", source)
                self.assertNotIn("import backend", source)


if __name__ == "__main__":
    unittest.main()
