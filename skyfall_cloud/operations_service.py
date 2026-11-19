"""Controlled cloud operations (Phase 9). Approval-gated."""

from __future__ import annotations

from typing import Any, Callable


class OperationsService:
    def __init__(self, approval_callback: Callable[[dict[str, Any]], bool] | None = None) -> None:
        self.approval_callback = approval_callback or (lambda plan: False)

    def plan_operation(self, operation: str, target: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"operation": operation, "target": target, "params": params or {},
                "requires_approval": True, "risk": "high" if operation.startswith("delete") else "medium"}

    def execute(self, plan: dict[str, Any]) -> dict[str, Any]:
        if not self.approval_callback(plan):
            return {"success": False, "error": "approval denied", "plan": plan}
        return {"success": True, "message": "approved (execution delegated to controlled runner)", "plan": plan}
