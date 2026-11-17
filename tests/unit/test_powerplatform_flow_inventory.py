from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

from skyfall_cloud.command_runner import CommandResult
from skyfall_cloud.powerplatform_resources import (
    PowerPlatformFlowInventory,
    PowerPlatformInventoryError,
    _extract_flow_rows,
)


ENVIRONMENT_ID = "11111111-2222-3333-4444-555555555555"


class FakeDiscovery:
    def __init__(self, authenticated: bool = True):
        self.authenticated = authenticated

    def get_auth_status(self):
        return {
            "authenticated": self.authenticated,
            "active_profile": {
                "label": "Lexmark QA",
                "user": "engineer@example.invalid",
                "index": 2,
            } if self.authenticated else None,
        }


class FakeRunner:
    def __init__(self, payload=None, *, returncode: int = 0, stderr: str = "", timed_out: bool = False):
        self.payload = payload if payload is not None else []
        self.returncode = returncode
        self.stderr = stderr
        self.timed_out = timed_out
        self.calls = []

    def __call__(self, executable, arguments, *, timeout_seconds=45, env_overrides=None):
        self.calls.append((executable, list(arguments), timeout_seconds, env_overrides))
        stdout = json.dumps(self.payload) if self.returncode == 0 else ""
        return CommandResult(
            executable=executable,
            returncode=self.returncode,
            stdout=stdout,
            stderr=self.stderr,
            timed_out=self.timed_out,
        )


class PowerPlatformFlowInventoryTests(unittest.TestCase):
    def _sample_payload(self):
        return {
            "value": [
                {
                    "workflowId": "flow-001",
                    "displayName": "Daily invoice notification",
                    "state": "Started",
                    "flowType": "Automated",
                    "owner": {
                        "displayName": "Platform Team",
                        "email": "platform@example.invalid",
                    },
                    "createdTime": "2026-10-01T10:00:00Z",
                    "lastModifiedTime": "2026-11-10T12:30:00Z",
                    # Must never be returned, serialized or exported.
                    "definition": {"actions": {"SensitiveAction": {"inputs": "do-not-export"}}},
                    "connectionReferences": {"shared_secret": "do-not-export-secret"},
                },
                {
                    "workflowId": "flow-002",
                    "displayName": '=HYPERLINK("https://example.invalid","Click")',
                    "state": "Stopped",
                    "flowType": "Instant",
                    "owner": {"displayName": "Operations"},
                    "createdTime": "2026-10-02T10:00:00Z",
                    "lastModifiedTime": "2026-11-11T12:30:00Z",
                },
            ]
        }

    def test_inventory_creates_descriptively_named_workbook_and_exports_allowlisted_metadata(self):
        runner = FakeRunner(self._sample_payload())
        with tempfile.TemporaryDirectory() as temp_dir:
            service = PowerPlatformFlowInventory(
                project_root=temp_dir,
                runner=runner,
                discovery=FakeDiscovery(),
            )
            result = service.inventory(
                environment_id=ENVIRONMENT_ID,
                environment_name="IT.CRM.QA",
                generate_excel=True,
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["flow_count"], 2)
            self.assertEqual(result["enabled_count"], 1)
            self.assertEqual(result["disabled_or_suspended_count"], 1)
            self.assertEqual(result["owner_count"], 2)
            self.assertIn("Platform Team", {item["owner"] for item in result["preview"]})
            self.assertFalse(result["cloud_resources_modified"])
            self.assertFalse(result["secrets_returned"])
            self.assertFalse(result["flow_definitions_read"])
            self.assertEqual(len(runner.calls), 1)
            self.assertEqual(
                runner.calls[0][1],
                ["power-automate", "list-cloud-flows", "--environment", ENVIRONMENT_ID, "--json"],
            )

            report_path = Path(result["report"]["path"])
            self.assertTrue(report_path.is_file())
            self.assertRegex(
                report_path.name,
                r"^Power-Automate-Flows-IT-CRM-QA-\d{4}-\d{2}-\d{2}(?:-\d{2})?\.xlsx$",
            )
            workbook = load_workbook(report_path, data_only=True)
            self.assertEqual(
                workbook.sheetnames,
                ["Overview", "Cloud Flows", "Status Summary", "Flow Types", "Owners", "Discovery Notes"],
            )
            flows_sheet = workbook["Cloud Flows"]
            headers = [cell.value for cell in flows_sheet[1]]
            name_col = headers.index("Flow name") + 1
            flow_names = [flows_sheet.cell(row=row, column=name_col).value for row in (2, 3)]
            self.assertTrue(any(isinstance(value, str) and value.startswith("'=HYPERLINK") for value in flow_names))
            serialized = repr(list(flows_sheet.values))
            self.assertNotIn("do-not-export", serialized)
            self.assertNotIn("do-not-export-secret", serialized)
            # No formula cells are created from untrusted flow metadata.
            self.assertFalse(any(cell.data_type == "f" for row in flows_sheet.iter_rows() for cell in row))
            workbook.close()

    def test_inventory_does_not_call_pac_when_profile_is_not_authenticated(self):
        runner = FakeRunner(self._sample_payload())
        service = PowerPlatformFlowInventory(
            runner=runner,
            discovery=FakeDiscovery(authenticated=False),
        )
        result = service.inventory(environment_id=ENVIRONMENT_ID)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_authenticated")
        self.assertEqual(runner.calls, [])

    def test_invalid_environment_id_is_rejected_before_pac_call(self):
        runner = FakeRunner(self._sample_payload())
        service = PowerPlatformFlowInventory(runner=runner, discovery=FakeDiscovery())
        with self.assertRaisesRegex(ValueError, "valid GUID"):
            service.inventory(environment_id="QA")
        self.assertEqual(runner.calls, [])

    def test_test_mode_blocks_before_authentication_or_cli(self):
        runner = FakeRunner(self._sample_payload())
        discovery = FakeDiscovery()
        with patch.dict(os.environ, {"SKYFALL_TEST_MODE": "1"}):
            service = PowerPlatformFlowInventory(runner=runner, discovery=discovery)
            result = service.inventory(environment_id=ENVIRONMENT_ID)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "blocked_test_mode")
        self.assertEqual(runner.calls, [])

    def test_permission_failure_returns_friendly_error_without_raw_cli_output(self):
        runner = FakeRunner(returncode=1, stderr="403 Forbidden: detailed internal response")
        service = PowerPlatformFlowInventory(runner=runner, discovery=FakeDiscovery())
        with self.assertRaises(PowerPlatformInventoryError) as context:
            service.inventory(environment_id=ENVIRONMENT_ID)
        self.assertIn("sufficient permission", str(context.exception))
        self.assertNotIn("detailed internal response", str(context.exception))

    def test_duplicate_flow_ids_are_deduplicated_and_sensitive_objects_are_ignored(self):
        rows = _extract_flow_rows({
            "flows": [
                {"workflowId": "same-id", "displayName": "First"},
                {"workflowId": "same-id", "displayName": "Duplicate", "definition": {"x": "secret"}},
                {"displayName": "No identifier", "state": "Started"},
            ]
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["flow_name"], "First")
        self.assertNotIn("definition", rows[0])

    def test_zero_counts_are_preserved_in_report_tables(self):
        from openpyxl import Workbook
        from skyfall_cloud.powerplatform_resources import PowerPlatformFlowInventory as Inventory

        workbook = Workbook()
        sheet = workbook.active
        Inventory._append_table(sheet, [("Metric", "label"), ("Count", "count")], [{"label": "Disabled", "count": 0}], "ZeroCountTable")
        self.assertEqual(sheet.cell(row=2, column=2).value, 0)
        workbook.close()


if __name__ == "__main__":
    unittest.main()
