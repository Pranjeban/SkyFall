"""Contract tests for v1.1 Module 11 governance (no persistence/network)."""

from __future__ import annotations

import unittest
from datetime import datetime

from skyfall_cloud.cloud_governance import CloudGovernanceService

TOKEN = "GOV_SECRET_TOKEN"


class TestCloudGovernance(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CloudGovernanceService()

    def test_redact_recursive_idempotent(self) -> None:
        payload = {"access_token": TOKEN, "note": f"Bearer {TOKEN}", "monkey": "safe"}
        once = self.service.redact(payload)
        self.assertEqual(once, self.service.redact(once))
        self.assertNotIn(TOKEN, str(once))
        self.assertEqual(once["monkey"], "safe")

    def test_record_redacts_and_sequences(self) -> None:
        first = self.service.record(
            "tool_call", provider="azure", profile_id="az-1",
            action="list_resources", outcome=f"failed: Bearer {TOKEN}",
            details={"token": TOKEN},
        )
        second = self.service.record("tool_call", provider="powerplatform")
        self.assertEqual(first["sequence"], 1)
        self.assertEqual(second["sequence"], 2)
        self.assertNotIn(TOKEN, str(first))
        self.assertIsInstance(datetime.fromisoformat(first["timestamp"]), datetime)

    def test_entries_are_copies_and_filtered(self) -> None:
        self.service.record("tool_call", provider="azure")
        self.service.record("policy", provider="powerplatform")
        rows = self.service.entries(event="tool_call")
        self.assertEqual(len(rows), 1)
        rows[0]["event"] = "mutated"
        self.assertEqual(self.service.entries()[0]["event"], "tool_call")
        self.assertEqual(len(self.service.entries(provider="powerplatform")), 1)
        self.assertEqual(len(self.service.entries(limit=1)), 1)

    def test_policy_allows_read_only(self) -> None:
        decision = self.service.evaluate_policy(
            "azure.list_resources", provider="azure", profile_provider="azure"
        )
        self.assertTrue(decision["allowed"])
        self.assertFalse(decision["requires_approval"])
        self.assertEqual(decision["reasons"], [])

    def test_policy_denies_mutating_operations(self) -> None:
        for op in ("azure.delete_resource", "powerplatform.update_flow", "run_script"):
            with self.subTest(op=op):
                decision = self.service.evaluate_policy(op)
                self.assertFalse(decision["allowed"])
                self.assertTrue(decision["requires_approval"])

    def test_policy_denies_provider_mismatch(self) -> None:
        decision = self.service.evaluate_policy(
            "powerplatform.list_flows",
            provider="powerplatform",
            profile_provider="azure",
        )
        self.assertFalse(decision["allowed"])
        self.assertTrue(any("provider" in reason for reason in decision["reasons"]))

    def test_explicit_approval_flag(self) -> None:
        decision = self.service.evaluate_policy("azure.get_resource", requires_approval=True)
        self.assertTrue(decision["allowed"])
        self.assertTrue(decision["requires_approval"])

    def test_summary_counts(self) -> None:
        self.service.record("tool_call", provider="azure", outcome="success")
        self.service.record("tool_call", provider="azure", outcome="success")
        self.service.record("policy", provider="powerplatform", outcome="denied")
        summary = self.service.summary()
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["by_event"]["tool_call"], 2)
        self.assertEqual(summary["by_outcome"]["denied"], 1)
        self.assertEqual(summary["by_provider"]["azure"], 2)


if __name__ == "__main__":
    unittest.main()
