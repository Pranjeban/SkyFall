from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skyfall_workspace.manager import WorkspaceManager
from skyfall_mcp.tools.workspace import (
    describe_workspace_file,
    get_workspace_index_status,
    list_workspaces,
    search_workspace_files,
)


class WorkspaceMcpToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data_root = self.root / "localappdata"
        self.data_root.mkdir()
        self.workspace = self.root / "sample_workspace"
        self.workspace.mkdir()
        (self.workspace / "InspectEnvironment.ps1").write_text(
            "param([string]$EnvironmentName)\n"
            "function Get-EnvironmentInventory { }\n",
            encoding="utf-8",
        )
        self.env_patch = patch.dict(os.environ, {"LOCALAPPDATA": str(self.data_root)})
        self.env_patch.start()
        self.manager = WorkspaceManager()
        self.record = self.manager.add_workspace(self.workspace, allow_ai_metadata=True)
        self.manager.scan_workspace(self.record.id)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp.cleanup()

    def test_workspace_tools_return_metadata_only(self) -> None:
        status = json.loads(get_workspace_index_status())
        self.assertEqual(status["ai_visible_workspaces"], 1)
        self.assertFalse(status["source_contents_shared"])

        listing = json.loads(list_workspaces())
        self.assertEqual(listing["count"], 1)
        self.assertFalse(listing["source_contents_shared"])
        self.assertNotIn("scan_error", listing["workspaces"][0])

        search = json.loads(search_workspace_files("InspectEnvironment", "powershell", "", 10))
        self.assertEqual(search["count"], 1)
        self.assertFalse(search["source_contents_shared"])
        result = search["results"][0]
        self.assertNotIn("sha256", result)

        described = json.loads(describe_workspace_file(result["file_id"]))
        self.assertFalse(described["source_contents_shared"])
        self.assertEqual(described["file"]["name"], "InspectEnvironment.ps1")
        self.assertNotIn("sha256", described["file"])
        self.assertNotIn("param([string]$EnvironmentName)", json.dumps(described))

    def test_no_consent_means_no_workspace_tool_visibility(self) -> None:
        self.manager.set_ai_metadata_access(self.record.id, False)
        self.assertEqual(json.loads(list_workspaces())["count"], 0)
        self.assertEqual(json.loads(search_workspace_files("InspectEnvironment"))["count"], 0)


if __name__ == "__main__":
    unittest.main()
