"""Contract tests for v1.1 Module 9 controlled operations gate.

No cloud calls, no credentials and no execution are involved.
"""

from __future__ import annotations

import unittest

from skyfall_cloud.controlled_operations import (
    ControlledOperationsError,
    ControlledOperationsService,
    OperationRequest,
    OperationRisk,
)

SECRET = b"test-only-approval-secret"
APPROVER = "engineer@example.com"


class TestControlledOperations(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = {"now": 1_700_000_000.0}
        self.service = ControlledOperationsService(
            approval_secret=SECRET, now=lambda: self.clock["now"]
        )

    @staticmethod
    def _read() -> OperationRequest:
        return OperationRequest("azure.list_resources", "azure", "/subscriptions/s1")

    @staticmethod
    def _reversible() -> OperationRequest:
        return OperationRequest("azure.reindex_resource", "azure", "/subscriptions/s1")

    @staticmethod
    def _destructive() -> OperationRequest:
        return OperationRequest("azure.delete_resource", "azure", "/subscriptions/s1")

    def test_classify_read_only(self) -> None:
        self.assertEqual(self.service.classify(self._read()), OperationRisk.READ_ONLY)

    def test_classify_destructive(self) -> None:
        self.assertEqual(
            self.service.classify(self._destructive()), OperationRisk.DESTRUCTIVE
        )

    def test_classify_reversible(self) -> None:
        self.assertEqual(
            self.service.classify(self._reversible()), OperationRisk.REVERSIBLE
        )

    def test_invalid_input_rejected(self) -> None:
        for request in (
            OperationRequest("BAD OP", "azure", "x"),
            OperationRequest("azure.list_resources", "unknown", "x"),
            OperationRequest("azure.list_resources", "azure", "../../evil"),
            OperationRequest("azure.list_resources", "azure", ""),
        ):
            with self.subTest(request=request):
                with self.assertRaises(ControlledOperationsError):
                    self.service.build_plan(request)

    def test_build_plan_read_only(self) -> None:
        plan = self.service.build_plan(self._read())
        self.assertEqual(plan["risk"], "read_only")
        self.assertTrue(plan["execution_permitted"])
        self.assertFalse(plan["approved"])
        self.assertEqual(plan["steps"][0], "validate_profile")
        self.assertFalse(plan["token_material_returned"])

    def test_approval_issued_and_verified(self) -> None:
        plan = self.service.build_plan(self._reversible())
        approved = self.service.request_approval(plan, approver=APPROVER, ttl_seconds=60)
        self.assertTrue(approved["approved"])
        self.assertIn(".", approved["approval_token"])
        self.assertTrue(
            self.service.verify_approval(approved, approved["approval_token"], approver=APPROVER)
        )

    def test_approval_token_cannot_be_replayed(self) -> None:
        approved = self.service.request_approval(
            self.service.build_plan(self._reversible()), approver=APPROVER
        )
        self.assertTrue(
            self.service.verify_approval(approved, approved["approval_token"], approver=APPROVER)
        )
        self.assertFalse(
            self.service.verify_approval(approved, approved["approval_token"], approver=APPROVER)
        )

    def test_tampered_plan_rejected(self) -> None:
        approved = self.service.request_approval(
            self.service.build_plan(self._reversible()), approver=APPROVER
        )
        tampered = {**approved, "request": {**approved["request"], "target": "/subscriptions/other"}}
        self.assertFalse(
            self.service.verify_approval(tampered, approved["approval_token"], approver=APPROVER)
        )

    def test_wrong_approver_and_expiry_rejected(self) -> None:
        approved = self.service.request_approval(
            self.service.build_plan(self._reversible()), approver=APPROVER, ttl_seconds=60
        )
        self.assertFalse(
            self.service.verify_approval(approved, approved["approval_token"], approver="other@example.com")
        )
        self.clock["now"] += 61
        self.assertFalse(
            self.service.verify_approval(approved, approved["approval_token"], approver=APPROVER)
        )

    def test_destructive_cannot_be_approved_or_simulated(self) -> None:
        plan = self.service.build_plan(self._destructive())
        self.assertEqual(plan["steps"], ["blocked_by_policy"])
        with self.assertRaises(ControlledOperationsError):
            self.service.request_approval(plan, approver=APPROVER)
        result = self.service.simulate(plan, "anything", approver=APPROVER)
        self.assertFalse(result["success"])
        self.assertIn("blocked", result["error"].lower())

    def test_simulate_requires_valid_approval(self) -> None:
        plan = self.service.build_plan(self._reversible())
        denied = self.service.simulate(plan, "bad.token", approver=APPROVER)
        self.assertFalse(denied["success"])
        approved = self.service.request_approval(plan, approver=APPROVER)
        result = self.service.simulate(approved, approved["approval_token"], approver=APPROVER)
        self.assertTrue(result["success"])
        self.assertTrue(result["simulated"])
        self.assertFalse(result["executed"])
        self.assertFalse(result["token_material_returned"])

    def test_read_only_plan_needs_no_approval(self) -> None:
        plan = self.service.build_plan(self._read())
        with self.assertRaises(ControlledOperationsError):
            self.service.request_approval(plan, approver=APPROVER)
        result = self.service.simulate(plan, "", approver=APPROVER)
        self.assertTrue(result["success"])
        self.assertFalse(result["executed"])

    def test_execute_always_refuses(self) -> None:
        result = self.service.execute(self._read(), approver=APPROVER)
        self.assertFalse(result["success"])
        self.assertFalse(result["enabled"])

    def test_policy_description(self) -> None:
        policy = self.service.describe_policy()
        self.assertFalse(policy["execution_enabled"])
        self.assertIn("azure.list_resources", policy["read_only_operations"])
        self.assertIn("delete", policy["destructive_verbs"])


if __name__ == "__main__":
    unittest.main()
