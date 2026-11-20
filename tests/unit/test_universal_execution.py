from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

from skyfall_cloud.universal_execution import (
    ApprovalStatus,
    ExecutionMode,
    ExecutionRequest,
    FailureType,
    PlanStatus,
    UniversalExecutionEngine,
    VerificationStatus,
    redact_public_text,
)
from skyfall_mcp.registry import CapabilityRegistry
from skyfall_mcp.tools import unified_cloud


SECRET = "Bearer eyJAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


class FakeWorkspaceManager:
    def __init__(
        self,
        *,
        allow_ai: bool = True,
        result: dict | None = None,
        flat_result: bool = False,
        describe_error: str | None = None,
    ):
        self.allow_ai = allow_ai
        self.flat_result = flat_result
        self.describe_error = describe_error
        self.result = result or {
            "file_id": "file-1",
            "workspace_id": "ws-1",
            "name": "script.ps1",
            "relative_path": "scripts/script.ps1",
            "file_type": "powershell",
        }
        self.calls = []

    def get_workspace(self, workspace_id):
        self.calls.append(("get_workspace", workspace_id))

        class WS:
            allow_ai_metadata = self.allow_ai

        return WS() if workspace_id else None

    def search_for_ai(self, query, workspace_id=None):
        self.calls.append(("search_for_ai", query, workspace_id))
        if not self.allow_ai:
            return []
        return [dict(self.result)]

    def describe_file_for_ai(self, file_id):
        self.calls.append(("describe_file_for_ai", file_id))
        if self.describe_error:
            raise KeyError(self.describe_error)
        if not self.allow_ai:
            return {"success": False, "error": "Workspace AI metadata consent is not available."}
        if file_id != self.result.get("file_id"):
            return {"success": False, "error": "File not found."}
        if self.flat_result:
            return dict(self.result)
        return {"success": True, "file": dict(self.result)}

    def list_for_ai(self):
        self.calls.append(("list_for_ai",))
        return []


class UniversalExecutionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = UniversalExecutionEngine(approval_secret=b"test-secret", history_limit=3)

    def test_mcp_first_resolution_and_failure_types(self) -> None:
        resolution, plan, _ = self.engine.plan(ExecutionRequest(capability_id="core.get_status"))
        self.assertTrue(resolution.resolved)
        self.assertEqual(resolution.source, "mcp")
        self.assertEqual(plan.status, PlanStatus.PLANNED)
        self.assertEqual(plan.failure_type, FailureType.NONE)

        missing = self.engine.resolve(ExecutionRequest(operation="does.not.exist"))
        self.assertFalse(missing.resolved)
        self.assertEqual(missing.failure_type, FailureType.CAPABILITY_NOT_FOUND)
        self.assertEqual(self.engine.classify_failure("approval_required"), FailureType.APPROVAL_REQUIRED)

    def test_workspace_fallback_requires_explicit_request_and_ai_metadata_api(self) -> None:
        manager = FakeWorkspaceManager()
        engine = UniversalExecutionEngine(workspace_manager=manager, approval_secret=b"test-secret")
        no_fallback = engine.resolve(ExecutionRequest(file_id="file-1", query="script"))
        self.assertFalse(no_fallback.resolved)
        self.assertEqual(no_fallback.failure_type, FailureType.WORKSPACE_FALLBACK_NOT_ALLOWED)
        self.assertEqual(manager.calls, [])

        resolution = engine.resolve(
            ExecutionRequest(
                allow_workspace_fallback=True,
                file_id="file-1",
                provider="workspace",
                operation="workspace.plan_script",
            )
        )
        self.assertTrue(resolution.resolved)
        self.assertEqual(resolution.source, "workspace")
        self.assertEqual(resolution.file_id, "file-1")
        self.assertEqual(resolution.relative_path, "scripts/script.ps1")
        self.assertTrue(any(call[0] == "describe_file_for_ai" for call in manager.calls))
        # store only IDs/relative metadata
        payload = resolution.to_dict()
        self.assertNotIn("C:\\", json.dumps(payload))
        self.assertNotIn("/Users/", json.dumps(payload))
        self.assertNotIn("content", json.dumps(payload).lower())

    def test_revoked_consent_blocks_workspace_fallback(self) -> None:
        manager = FakeWorkspaceManager(allow_ai=False)
        engine = UniversalExecutionEngine(workspace_manager=manager, approval_secret=b"test-secret")
        resolution = engine.resolve(
            ExecutionRequest(allow_workspace_fallback=True, file_id="file-1", operation="workspace.plan_script")
        )
        self.assertFalse(resolution.resolved)
        self.assertEqual(resolution.failure_type, FailureType.CONSENT_REVOKED)

    def test_real_workspace_manager_flat_result_shape_is_supported(self) -> None:
        manager = FakeWorkspaceManager(flat_result=True)
        engine = UniversalExecutionEngine(
            workspace_manager=manager, approval_secret=b"test-secret"
        )
        resolution = engine.resolve(
            ExecutionRequest(
                allow_workspace_fallback=True,
                file_id="file-1",
                operation="workspace.plan_script",
            )
        )
        self.assertTrue(resolution.resolved)
        self.assertEqual(resolution.source, "workspace")
        self.assertEqual(resolution.relative_path, "scripts/script.ps1")
        payload = resolution.to_dict()
        self.assertNotIn("absolute_path", json.dumps(payload))
        self.assertNotIn("sha256", json.dumps(payload))

        revoked = FakeWorkspaceManager(
            describe_error="File not found, not indexed, or workspace metadata sharing is not enabled."
        )
        denied = UniversalExecutionEngine(
            workspace_manager=revoked, approval_secret=b"test-secret"
        ).resolve(
            ExecutionRequest(
                allow_workspace_fallback=True,
                file_id="file-1",
                operation="workspace.plan_script",
            )
        )
        self.assertFalse(denied.resolved)
        self.assertEqual(denied.failure_type, FailureType.CONSENT_REVOKED)

    def test_mcp_engine_is_wired_to_workspace_manager(self) -> None:
        manager = FakeWorkspaceManager(flat_result=True)
        with patch("skyfall_mcp.tools.unified_cloud.WorkspaceManager", return_value=manager):
            unified_cloud.configure_unified_cloud_services()
            try:
                payload = json.loads(
                    unified_cloud.plan_execution(
                        allow_workspace_fallback=True,
                        file_id="file-1",
                        operation="workspace.plan_script",
                    )
                )
                self.assertEqual(payload["resolution"]["source"], "workspace")
                self.assertTrue(payload["resolution"]["resolved"])
                self.assertFalse(payload["executed"])
            finally:
                unified_cloud.configure_unified_cloud_services()

    def test_redaction_and_no_secret_leakage(self) -> None:
        unc = r"\\server\share\script.ps1"
        forward_drive = r"C:/secret/path.txt"
        text = redact_public_text(
            f"Authorization: {SECRET} token=abc123 C:\\secret\\path.txt "
            f"/tmp/secret {unc} {forward_drive}"
        )
        self.assertNotIn("eyJ", text)
        self.assertNotIn("abc123", text)
        self.assertNotIn("C:\\secret", text)
        self.assertNotIn("/tmp/secret", text)
        self.assertNotIn("server\\share", text)
        self.assertNotIn("C:/secret", text)
        self.assertIn("[REDACTED]", text)

    def test_approval_binding_one_time_and_mutating_simulation(self) -> None:
        req = ExecutionRequest(
            operation="workspace.plan_script",
            provider="workspace",
            allow_workspace_fallback=True,
            file_id="file-1",
            requires_mutation=True,
        )
        engine = UniversalExecutionEngine(
            workspace_manager=FakeWorkspaceManager(), approval_secret=b"test-secret"
        )
        _, plan, _ = engine.plan(req)
        self.assertTrue(plan.mutable)
        self.assertEqual(plan.approval_status, ApprovalStatus.REQUIRED)

        missing, _ = engine.simulate(plan)
        self.assertFalse(missing.success)
        self.assertEqual(missing.failure_type, FailureType.APPROVAL_REQUIRED)
        self.assertFalse(missing.executed)

        token = engine.issue_plan_approval(plan, "approver@example.com", ttl_seconds=60)
        ok, record = engine.simulate(plan, approval_token=token, approver="approver@example.com")
        self.assertTrue(ok.success)
        self.assertTrue(ok.simulated)
        self.assertFalse(ok.executed)
        self.assertEqual(ok.verification.status, VerificationStatus.PASSED)
        self.assertEqual(record.plan.approval_status, ApprovalStatus.BOUND)

        replay, _ = engine.simulate(plan, approval_token=token, approver="approver@example.com")
        self.assertFalse(replay.success)
        self.assertEqual(replay.failure_type, FailureType.APPROVAL_INVALID)

    def test_approval_token_is_bound_to_full_plan(self) -> None:
        req = ExecutionRequest(
            operation="workspace.plan_script",
            provider="workspace",
            allow_workspace_fallback=True,
            file_id="file-1",
            requires_mutation=True,
        )
        engine = UniversalExecutionEngine(
            workspace_manager=FakeWorkspaceManager(), approval_secret=b"test-secret"
        )
        _, first_plan, _ = engine.plan(req)
        token = engine.issue_plan_approval(first_plan, "approver@example.com", ttl_seconds=60)

        _, second_plan, _ = engine.plan(req)
        self.assertNotEqual(first_plan.plan_id, second_plan.plan_id)
        result, _ = engine.simulate(
            second_plan, approval_token=token, approver="approver@example.com"
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, FailureType.APPROVAL_INVALID)

    def test_no_subprocess_and_steps_only_simulation(self) -> None:
        with patch("subprocess.run", side_effect=AssertionError("subprocess.run called")) as run_mock, patch(
            "subprocess.Popen", side_effect=AssertionError("subprocess.Popen called")
        ) as popen_mock:
            _, plan, _ = self.engine.plan(ExecutionRequest(capability_id="core.get_status"))
            result, _ = self.engine.simulate(plan)
        self.assertFalse(run_mock.called)
        self.assertFalse(popen_mock.called)
        self.assertFalse(result.executed)
        self.assertTrue(result.simulated)
        self.assertTrue(all(isinstance(step, dict) for step in result.steps))

    def test_verification_failure_and_history_bounds(self) -> None:
        _, plan, _ = self.engine.plan(ExecutionRequest(capability_id="core.get_status"))
        failed_result = type(
            "R",
            (),
            {
                "executed": True,
                "steps": (),
                "to_dict": lambda self: {},
            },
        )()
        verification = self.engine.verify(plan, failed_result)
        self.assertEqual(verification.status, VerificationStatus.FAILED)
        self.assertEqual(verification.failure_type, FailureType.VERIFICATION_FAILED)

        bounded = UniversalExecutionEngine(approval_secret=b"test-secret", history_limit=2)
        for cap in ("core.get_status", "core.list_capabilities", "core.describe_capability"):
            _, p, _ = bounded.plan(ExecutionRequest(capability_id=cap))
            bounded.simulate(p)
        history = bounded.list_history()
        self.assertEqual(len(history), 2)
        self.assertIsNotNone(bounded.get_record(history[0].request_id))

    def test_mcp_adapter_json_handling_and_redaction(self) -> None:
        engine = UniversalExecutionEngine(approval_secret=b"test-secret")
        unified_cloud.configure_unified_cloud_services(engine=engine)
        try:
            payload = json.loads(unified_cloud.plan_execution(capability_id="core.get_status"))
            self.assertTrue(payload["plan_only"])
            self.assertFalse(payload["executed"])
            self.assertFalse(payload["process_started"])
            self.assertIn("No process was started", payload["message"])
            self.assertIsNotNone(payload.get("plan"))

            history = json.loads(unified_cloud.get_execution_history(limit=5))
            self.assertTrue(history["success"])
            self.assertFalse(history["process_started"])
            self.assertIn("No process was started", history["message"])
            self.assertGreaterEqual(history["count"], 1)

            # adapter must not leak redacted secret material in failures/messages
            bad = json.loads(unified_cloud.plan_execution(operation=f"nope {SECRET}"))
            self.assertFalse(bad["executed"])
            self.assertFalse(bad["process_started"])
            self.assertNotIn("eyJ", json.dumps(bad))
        finally:
            unified_cloud.configure_unified_cloud_services()

    def test_operation_plan_adapter_redacts_caller_fields(self) -> None:
        unified_cloud.configure_unified_cloud_services()
        try:
            raw = unified_cloud.build_operation_plan(
                "azure.list_resources", "azure", r"C:\secret\run.ps1", "token=abc123"
            )
            self.assertNotIn("C:\\secret", raw)
            self.assertNotIn("abc123", raw)
            self.assertIn("[REDACTED]", raw)
        finally:
            unified_cloud.configure_unified_cloud_services()

    def test_no_subprocess_import_in_engine_module(self) -> None:
        import inspect
        import skyfall_cloud.universal_execution as mod

        source = inspect.getsource(mod)
        self.assertNotIn("import subprocess", source)
        self.assertNotIn("from subprocess", source)


if __name__ == "__main__":
    unittest.main()
