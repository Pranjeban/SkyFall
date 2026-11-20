"""Phase 10 integration acceptance tests (spec 10 Phase 10, lines 857-872).

STATIC source/contract checks only. This suite never imports Qt/PySide6,
constructs a widget, launches the GUI, spawns the MCP server or a FastAPI app,
opens the network or writes to the database. It reads project files as text and
asserts on stable substrings (no hard-coded line numbers).

Scope checked here: UI<->backend wiring, memory<->persistence wiring, MCP
registry/consumer, application lifecycle, error propagation, and the documented
(configuration) version split. Agent-behavior runtime integration is NOT
asserted (D20 pending). This is NOT an end-to-end run: D1 is PENDING, so no
"approved requirements" define E2E, and no GUI/live DB/server is available.
That limitation is recorded in the progress record.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_PY = REPO_ROOT / "main.py"
MAIN_WINDOW_PY = REPO_ROOT / "app" / "desktop" / "main_window.py"
COPILOT_SERVICE_PY = REPO_ROOT / "integrations" / "copilot" / "copilot_service.py"
MCP_SERVER_PY = REPO_ROOT / "skyfall_mcp" / "server.py"
VERSION_TXT = REPO_ROOT / "VERSION.txt"
CAPABILITIES_JSON = REPO_ROOT / "configuration" / "capabilities.json"
BACKEND_API_PY = REPO_ROOT / "backend" / "api.py"
BACKEND_ACCEPTANCE_PY = REPO_ROOT / "tests" / "unit" / "test_backend_acceptance.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestPhase10IntegrationAcceptance(unittest.TestCase):
    """Static verification of Phase 10 integration wiring and constraints."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.main_window = _read(MAIN_WINDOW_PY)
        cls.copilot = _read(COPILOT_SERVICE_PY)
        cls.mcp_server = _read(MCP_SERVER_PY)
        cls.main = _read(MAIN_PY)

    # --- Connect UI to backend services (:861) ---------------------------

    def test_ui_wires_copilot_worker_and_conversation_store(self) -> None:
        self.assertIn("from integrations.copilot.copilot_service import CopilotWorker", self.main_window)
        self.assertIn("from memory.conversation_store import", self.main_window)
        self.assertIn("CopilotWorker(", self.main_window)
        self.assertIn("ConversationStore()", self.main_window)

    def test_backend_api_stays_dormant(self) -> None:
        # Active UI source must not import the FastAPI skeleton (D21 pending).
        desktop_sources = "\n".join(
            p.read_text(encoding="utf-8")
            for p in sorted((REPO_ROOT / "app" / "desktop").glob("*.py"))
        )
        self.assertNotIn("backend.api", desktop_sources)
        self.assertNotIn("from backend", desktop_sources)
        self.assertTrue(BACKEND_API_PY.is_file())  # preserved, not deleted

    # --- Connect memory and persistence (:862) ---------------------------

    def test_memory_persistence_wired_to_ui(self) -> None:
        for call in (
            "get_or_create_active_conversation(",
            "add_message(",
            "set_sdk_session_initialized(",
            "list_conversations(",
            "get_messages(",
        ):
            self.assertIn(call, self.main_window)

    def test_callerless_store_methods_preserved(self) -> None:
        # The five methods with no UI caller stay present and untouched.
        acceptance = _read(BACKEND_ACCEPTANCE_PY)
        for method in (
            "update_conversation_title",
            "delete_message",
            "search_conversations",
            "export_conversation_markdown",
            "backup_database",
        ):
            self.assertIn(method, acceptance)

    # --- Verify MCP behavior (:865) --------------------------------------

    def test_mcp_tool_registry_has_all_tools(self) -> None:
        self.assertEqual(len(re.findall(r"@mcp\.tool", self.mcp_server)), 36)
        self.assertIn("def find_azure_function_app(", self.mcp_server)

    def test_app_reaches_mcp_via_sdk_config(self) -> None:
        self.assertIn("-m", self.copilot)
        self.assertIn("skyfall_mcp.server", self.copilot)
        self.assertIn("mcp_servers", self.copilot)

    # --- Validate application lifecycle (:866) ---------------------------

    def test_application_lifecycle_present(self) -> None:
        self.assertIn("QApplication(sys.argv)", self.main)
        self.assertIn("window.show()", self.main)
        self.assertIn("app.exec()", self.main)
        self.assertIn("def closeEvent", self.main_window)

    # --- Check error propagation (:867) ---------------------------------

    def test_error_propagation_paths_present(self) -> None:
        for token in (
            "couldn't connect to Copilot",
            "Copilot error",
            "Workspace database error",
        ):
            self.assertIn(token, self.main_window)

    # --- Check configuration consistency (:868) --------------------------

    def test_documented_version_split_is_unchanged(self) -> None:
        # D8 is PENDING: assert the known split, do NOT resolve it.
        self.assertIn("0.9.2", self.main)
        self.assertIn("0.9.2", _read(VERSION_TXT))
        self.assertIn("0.9.2", _read(CAPABILITIES_JSON))
        self.assertIn("1.0.1", _read(BACKEND_API_PY))

    # --- Agent behavior: no runtime integration asserted (D20 pending) ---

    def test_no_python_agent_roster_module(self) -> None:
        # D20 unmapped; no agent-behavior runtime integration exists to assert.
        self.assertFalse((REPO_ROOT / "skyfall_agents").is_dir())


if __name__ == "__main__":
    unittest.main()
