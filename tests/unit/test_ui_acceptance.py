"""Phase 9 UI acceptance tests (spec 10 Phase 9, lines 838-855).

Static source checks only. This suite NEVER imports Qt/PySide6, constructs a
widget, creates a QApplication, launches the GUI, opens the network or writes
to the database. It reads .py files as text and asserts on stable substrings
(no hard-coded line numbers, so it survives line shifts).

Exit-criterion context: "UI acceptance criteria pass and important historical
behavior is preserved." Because D1 (scope interpretation) is PENDING, no new
UI features are asserted here - only preservation of verified historical
behavior and the prior conservative fixes. This is a STATIC acceptance check,
not visual/interaction QA; that limitation is recorded in the progress record.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DESKTOP_DIR = REPO_ROOT / "app" / "desktop"
MAIN_WINDOW_PY = DESKTOP_DIR / "main_window.py"
THEME_PY = DESKTOP_DIR / "theme.py"
COMPONENTS_INIT = REPO_ROOT / "app" / "components" / "__init__.py"
FLOATING_INIT = REPO_ROOT / "app" / "floating" / "__init__.py"


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _desktop_sources() -> list[str]:
    return [_read_source(p) for p in sorted(DESKTOP_DIR.glob("*.py"))]


class TestPhase9UIAcceptance(unittest.TestCase):
    """Static verification of Phase 9 scope against the current source tree."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.main_window = _read_source(MAIN_WINDOW_PY)
        cls.desktop_sources = _desktop_sources()
        cls.all_desktop = "\n".join(cls.desktop_sources)

    # --- Prior fix SP-064: tool-count wording -----------------------------

    def test_tool_count_wording_present(self) -> None:
        self.assertIn("34 tools", self.main_window)
        self.assertIn("Thirty-four tools", self.main_window)

    def test_function_app_name_lookup_wiring_present(self) -> None:
        for token in (
            "which subscription is fn-qa-orders in?",
            "Find by name",
            "Function App name, e.g. fn-qa-orders",
            "azure_function_app_lookup",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.main_window)

    def test_no_stale_tool_count_wording(self) -> None:
        for source in self.desktop_sources:
            self.assertNotIn("19 tools", source)
            self.assertNotIn("Nineteen tools", source)

    # --- Prior fix SP-007/SP-008: labeled Delete control ------------------

    def test_delete_control_labeled_and_menu_retained(self) -> None:
        self.assertIn('QPushButton("Delete")', self.main_window)
        self.assertIn("QMenu(", self.main_window)

    def test_no_placeholder_text_in_production_ui(self) -> None:
        for source in self.desktop_sources:
            self.assertNotIn("???", source)

    # --- Historical table behavior: 5 read-only tables -------------------

    def test_five_read_only_tables_preserved(self) -> None:
        table_constructions = re.findall(r"=\s*QTableWidget\s*\(", self.main_window)
        self.assertGreaterEqual(len(table_constructions), 5)
        self.assertIn("NoEditTriggers", self.main_window)

    def test_no_sort_filter_or_row_action_features(self) -> None:
        # Phase 4 established these NEVER existed in v0.9.2 or v1.0.x; do not
        # treat their absence as a regression and do not invent them (D1 open).
        forbidden = (
            "setSortingEnabled",
            "sortItems",
            "setRowHidden",
            "itemChanged",
            "cellDoubleClicked",
            "cellClicked",
        )
        for source in self.desktop_sources:
            for token in forbidden:
                self.assertNotIn(token, source, f"{token} must not appear (historical behavior)")

    # --- spec :849 - no hardcoded demonstration data in production -------

    def test_no_hardcoded_demo_data_in_production(self) -> None:
        # Current production UI has zero demo/mock/fake/dummy dataset tokens.
        for source in self.desktop_sources:
            self.assertIsNone(re.search(r"\b(?:demo|mock|fake|dummy)\b", source, re.IGNORECASE))

    # --- spec :847 - loading / empty / error / success states -------------

    def test_loading_state_markers_present(self) -> None:
        for token in ("Starting...", "Connecting...", "QProgressBar", "in progress"):
            self.assertIn(token, self.all_desktop)

    def test_empty_state_markers_present(self) -> None:
        for token in ("emptyStateCard", "emptyStateTitle", "will appear here"):
            self.assertIn(token, self.all_desktop)

    def test_error_state_markers_present(self) -> None:
        for token in ("error_label", "could not be loaded", "could not be completed", "scan failed"):
            self.assertIn(token, self.all_desktop)

    def test_success_state_markers_present(self) -> None:
        for token in ("Inventory complete", "Report validated", '"success"'):
            self.assertIn(token, self.all_desktop)

    # --- Shell preservation (Phase 1 verdict) ----------------------------

    def test_theme_present_and_shells_empty(self) -> None:
        self.assertTrue(THEME_PY.is_file())
        for shell in (COMPONENTS_INIT, FLOATING_INIT):
            self.assertTrue(shell.is_file())
            nonblank = [line for line in _read_source(shell).splitlines() if line.strip()]
            self.assertEqual(nonblank, [], f"{shell} must remain an empty shell")


if __name__ == "__main__":
    unittest.main()
