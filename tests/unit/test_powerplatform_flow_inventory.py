from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook
from skyfall_cloud.powerplatform_resources import PowerPlatformFlowInventory, PowerPlatformInventoryError, _extract_flow_rows

ENVIRONMENT_ID = "11111111-2222-3333-4444-555555555555"
PROFILE_ID = "profile-qa"

class FakeStore:
    def __init__(self, profile=True):
        self.profile = {"profile_id": PROFILE_ID, "name": "QA", "username": "qa@example.invalid"} if profile else None
    def get_active_profile_id(self):
        return PROFILE_ID if self.profile else None
    def get_profile(self, profile_id=None):
        return self.profile if self.profile and profile_id in (None, PROFILE_ID) else None

class FakeApi:
    def __init__(self, rows=None, profile=True, error=None):
        self.store = FakeStore(profile)
        self.rows, self.error, self.calls = rows or [], error, []
    def list_flows(self, profile_id, environment_url):
        self.calls.append((profile_id, environment_url))
        if self.error:
            raise RuntimeError(self.error)
        return self.rows

class PowerPlatformFlowInventoryTests(unittest.TestCase):
    def rows(self):
        return [
            {"workflowId": "flow-1", "displayName": "Invoice flow", "state": "Enabled", "flowType": "Cloud flow", "owner": {"displayName": "Platform"}, "createdOn": "2026-10-01", "modifiedOn": "2026-11-01", "definition": {"secret": "never-export"}},
            {"workflowId": "flow-2", "displayName": "Disabled flow", "state": "Disabled", "flowType": "Cloud flow", "owner": {"displayName": "Operations"}},
        ]

    def test_inventory_generates_report_from_allowlisted_metadata(self):
        api = FakeApi(self.rows())
        with tempfile.TemporaryDirectory() as temp_dir:
            result = PowerPlatformFlowInventory(project_root=temp_dir, api=api).inventory(environment_id=ENVIRONMENT_ID, environment_name="IT.CRM.QA", environment_url="https://qa.crm.dynamics.com")
            self.assertTrue(result["success"])
            self.assertEqual(result["flow_count"], 2)
            self.assertEqual(result["enabled_count"], 1)
            self.assertEqual(api.calls, [(PROFILE_ID, "https://qa.crm.dynamics.com")])
            self.assertFalse(result["flow_definitions_read"])
            report = Path(result["report"]["path"])
            self.assertTrue(report.is_file())
            workbook = load_workbook(report, data_only=True)
            self.assertEqual(workbook.sheetnames, ["Overview", "Cloud Flows", "Status Summary", "Flow Types", "Owners", "Discovery Notes"])
            content = repr(list(workbook["Cloud Flows"].values))
            self.assertNotIn("never-export", content)
            self.assertIn("Dataverse Web API", repr(list(workbook["Overview"].values)))
            workbook.close()

    def test_resolves_environment_url_from_saved_environment_list(self):
        class ResolvingApi(FakeApi):
            def list_environments(self, profile_id):
                return {"success": True, "environments": [{"environment_id": ENVIRONMENT_ID, "name": "QA", "environment_url": "https://qa.crm.dynamics.com"}]}
        api = ResolvingApi(self.rows())
        result = PowerPlatformFlowInventory(api=api).inventory(environment_id=ENVIRONMENT_ID, generate_excel=False)
        self.assertTrue(result["success"])
        self.assertEqual(api.calls[0][1], "https://qa.crm.dynamics.com")

    def test_no_profile_or_invalid_environment_does_not_call_api(self):
        api = FakeApi(self.rows(), profile=False)
        result = PowerPlatformFlowInventory(api=api).inventory(environment_id=ENVIRONMENT_ID)
        self.assertFalse(result["success"])
        self.assertEqual(api.calls, [])
        with self.assertRaisesRegex(ValueError, "valid GUID"):
            PowerPlatformFlowInventory(api=api).inventory(environment_id="QA")

    def test_test_mode_blocks_api_calls(self):
        api = FakeApi(self.rows())
        with patch.dict(os.environ, {"SKYFALL_TEST_MODE": "1"}):
            result = PowerPlatformFlowInventory(api=api).inventory(environment_id=ENVIRONMENT_ID)
        self.assertEqual(result["status"], "blocked_test_mode")
        self.assertEqual(api.calls, [])

    def test_friendly_permission_error_and_deduplicated_metadata(self):
        api = FakeApi(error="Microsoft denied Dataverse flow metadata access. Internal detail")
        with self.assertRaisesRegex(PowerPlatformInventoryError, "Dataverse flow metadata access"):
            PowerPlatformFlowInventory(api=api).inventory(environment_id=ENVIRONMENT_ID, environment_url="https://qa.crm.dynamics.com")
        rows = _extract_flow_rows({"value": [{"workflowId": "same", "displayName": "First"}, {"workflowId": "same", "displayName": "Second", "definition": {"x": "secret"}}]})
        self.assertEqual(len(rows), 1)
        self.assertNotIn("definition", rows[0])

if __name__ == "__main__":
    unittest.main()
