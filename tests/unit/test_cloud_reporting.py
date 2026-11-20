"""Contract tests for v1.1 Module 8 reporting (no network/file writes)."""

from __future__ import annotations

import csv
import io
import unittest
from datetime import datetime

from skyfall_cloud.cloud_reporting import CloudReportingService

TOKEN = "REPORT_SECRET_TOKEN"


class TestCloudReporting(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CloudReportingService()

    def test_redact_is_recursive_and_idempotent(self) -> None:
        payload = {
            "access_token": TOKEN,
            "monkey": "safe-value",
            "note": f"Authorization: Bearer {TOKEN}",
            "nested": [{"client_secret": TOKEN}],
        }
        once = self.service.redact(payload)
        twice = self.service.redact(once)
        self.assertEqual(once, twice)
        self.assertNotIn(TOKEN, str(once))
        self.assertEqual(once["monkey"], "safe-value")

    def test_to_json_redacts_and_sorts(self) -> None:
        raw = self.service.to_json({"z": 1, "api_key": TOKEN})
        self.assertNotIn(TOKEN, raw)
        self.assertLess(raw.index('"api_key"'), raw.index('"z"'))

    def test_to_markdown_with_table(self) -> None:
        text = self.service.to_markdown("Report", {
            "Rows": [{"name": "a|b", "token": TOKEN}],
            "Notes": ["plain note"],
        })
        self.assertIn("# Report", text)
        self.assertIn("a\\|b", text)
        self.assertNotIn(TOKEN, text)
        self.assertIn("- plain note", text)

    def test_to_csv(self) -> None:
        self.assertEqual(self.service.to_csv([]), "")
        raw = self.service.to_csv([{"name": "a", "secret": TOKEN}], ["name", "secret"])
        rows = list(csv.DictReader(io.StringIO(raw)))
        self.assertEqual(rows[0]["name"], "a")
        self.assertNotIn(TOKEN, raw)

    def test_aggregate_counts(self) -> None:
        self.assertEqual(
            self.service.aggregate_counts([{"state": "b"}, {"state": "a"}, {"state": "b"}, None], "state"),
            {"a": 1, "b": 2},
        )

    def test_executive_report_shapes(self) -> None:
        report = self.service.build_executive_report(
            {"subscriptions": [{"id": "s1"}]},
            [{"environment_id": "e1", "access_token": TOKEN}],
            extra={"note": "ok"},
        )
        self.assertEqual(report["counts"]["azure_subscriptions"], 1)
        self.assertEqual(report["counts"]["powerplatform_environments"], 1)
        self.assertFalse(report["token_material_returned"])
        self.assertNotIn(TOKEN, str(report))
        self.assertIsInstance(datetime.fromisoformat(report["generated_at"]), datetime)
        self.assertIn("Executive Cloud Report", report["markdown"])


if __name__ == "__main__":
    unittest.main()
