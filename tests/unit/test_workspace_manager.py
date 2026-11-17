from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skyfall_workspace.manager import WorkspaceManager


class WorkspaceManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "engineering"
        self.workspace.mkdir()
        self.database = self.root / "skyfall_test.db"
        self.manager = WorkspaceManager(self.database)

        (self.workspace / "FetchFlows.ps1").write_text(
            "<#\n.SYNOPSIS\nFetches cloud flows for the selected environment.\n#>\n"
            "param([string]$EnvironmentId, [string]$EnvironmentUrl)\n"
            "Import-Module Microsoft.PowerApps.Administration.PowerShell\n"
            "function Get-CloudFlows { }\n",
            encoding="utf-8",
        )
        (self.workspace / "inventory.py").write_text(
            "import requests\n\n"
            "def fetch_inventory(subscription_id):\n    return []\n\n"
            "class InventoryReport:\n    pass\n",
            encoding="utf-8",
        )
        (self.workspace / "README.md").write_text(
            "# Automation Workspace\n\n"
            "This project contains scripts for operational inventory.\n\n"
            "## Flow inventory\n",
            encoding="utf-8",
        )
        (self.workspace / ".env").write_text(
            "CLIENT_SECRET=should-not-be-indexed\n", encoding="utf-8"
        )
        (self.workspace / "unsafe.ps1").write_text(
            '$client_secret = "this-is-a-long-test-secret-value"\n'
            "Write-Output 'not indexed for AI'\n",
            encoding="utf-8",
        )
        (self.workspace / "appsettings.json").write_text(
            '{"password": "a-long-private-test-value"}', encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_add_and_scan_workspace_is_local_only_by_default(self) -> None:
        record = self.manager.add_workspace(self.workspace)
        self.assertFalse(record.allow_ai_metadata)
        result = self.manager.scan_workspace(record.id)
        self.assertEqual(result["scan_status"], "complete")
        self.assertGreaterEqual(result["indexed_files"], 3)
        self.assertFalse(result["source_contents_persisted"])
        self.assertEqual(self.manager.search_for_ai("FetchFlows"), [])
        local = self.manager.search_local("FetchFlows", file_type="powershell")
        self.assertEqual(len(local), 1)
        self.assertEqual(local[0]["name"], "FetchFlows.ps1")
        self.assertIn("EnvironmentId", local[0]["parameters"])
        self.assertIn("Get-CloudFlows", local[0]["functions"])
        database_bytes = self.database.read_bytes()
        self.assertNotIn(b"Fetches cloud flows for the selected environment", database_bytes)
        self.assertNotIn(b"param([string]$EnvironmentId", database_bytes)

    def test_ai_search_requires_explicit_per_workspace_consent(self) -> None:
        record = self.manager.add_workspace(self.workspace)
        self.manager.scan_workspace(record.id)
        self.manager.set_ai_metadata_access(record.id, True)

        listed = self.manager.list_for_ai()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], record.id)

        results = self.manager.search_for_ai("FetchFlows", file_type="powershell")
        self.assertEqual(len(results), 1)
        file_id = results[0]["file_id"]
        described = self.manager.describe_file_for_ai(file_id)
        self.assertEqual(described["name"], "FetchFlows.ps1")
        serialized = json.dumps(described)
        self.assertNotIn("Fetches cloud flows for the selected environment", serialized)
        self.assertNotIn("param([string]$EnvironmentId", serialized)
        self.assertNotIn("this-is-a-long-test-secret-value", serialized)

    def test_detected_secret_bearing_files_are_excluded_from_ai_search(self) -> None:
        record = self.manager.add_workspace(self.workspace, allow_ai_metadata=True)
        self.manager.scan_workspace(record.id)
        results = self.manager.search_for_ai("unsafe", file_type="powershell")
        self.assertEqual(results, [])
        self.assertEqual(self.manager.search_local("unsafe", file_type="powershell"), [])
        self.assertEqual(self.manager.search_for_ai("appsettings", file_type="json"), [])

    def test_env_files_are_never_indexed(self) -> None:
        record = self.manager.add_workspace(self.workspace, allow_ai_metadata=True)
        self.manager.scan_workspace(record.id)
        results = self.manager.search_local(".env")
        self.assertEqual(results, [])

    def test_common_secret_assignment_patterns_are_excluded_from_search(self) -> None:
        credential_file = self.workspace / "configuration.yaml"
        credential_file.write_text(
            'azure_client_secret: "test-secret-value-long-enough"\n',
            encoding="utf-8",
        )
        record = self.manager.add_workspace(self.workspace, allow_ai_metadata=True)
        self.manager.scan_workspace(record.id)
        self.assertEqual(
            self.manager.search_for_ai("configuration.yaml", file_type="yaml"),
            [],
        )

    def test_local_azure_credential_directories_are_skipped(self) -> None:
        azure_profile = self.workspace / ".azure"
        azure_profile.mkdir()
        (azure_profile / "profile.json").write_text(
            '{"subscription": "example"}', encoding="utf-8"
        )
        record = self.manager.add_workspace(self.workspace)
        self.manager.scan_workspace(record.id)
        self.assertEqual(self.manager.search_local("profile.json"), [])

    def test_entire_user_profile_is_rejected_as_workspace_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "specific folder"):
            self.manager.add_workspace(Path.home())

    def test_removing_workspace_does_not_delete_source_folder(self) -> None:
        record = self.manager.add_workspace(self.workspace)
        self.manager.scan_workspace(record.id)
        self.manager.remove_workspace(record.id)
        self.assertTrue(self.workspace.is_dir())
        self.assertTrue((self.workspace / "FetchFlows.ps1").is_file())
        self.assertEqual(self.manager.list_workspaces(), [])

    def test_ai_index_status_exposes_only_opted_in_scope(self) -> None:
        local = self.manager.add_workspace(self.workspace)
        self.manager.scan_workspace(local.id)
        status = self.manager.get_ai_index_status()
        self.assertEqual(status["ai_visible_workspaces"], 0)
        self.manager.set_ai_metadata_access(local.id, True)
        status = self.manager.get_ai_index_status()
        self.assertEqual(status["ai_visible_workspaces"], 1)
        self.assertFalse(status["source_contents_shared"])


if __name__ == "__main__":
    unittest.main()
