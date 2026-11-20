"""Controlled resource and workflow operations (v1.1 Module 9).

A plan-and-approval gate for cloud operations. This module deliberately does NOT
execute anything: it classifies requests, builds deterministic plans, issues
short-lived HMAC approval tokens bound to the exact plan, and offers a dry-run
simulation. Real execution requires a separately authorised runner and is
intentionally out of scope for this read-only build.

No credentials, tokens or raw error bodies are ever placed in results.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

DEFAULT_TTL_SECONDS = 900
_OPERATION_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{1,79}$")
_PROVIDERS = frozenset({"azure", "powerplatform", "mcp", "workspace"})


class OperationRisk(str, Enum):
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    DESTRUCTIVE = "destructive"


class ControlledOperationsError(RuntimeError):
    """User-facing operations failure; never contains credential material."""


@dataclass(frozen=True)
class OperationRequest:
    operation: str
    provider: str
    target: str
    profile_id: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)


READ_ONLY_OPERATIONS = frozenset({
    "azure.list_tenants",
    "azure.list_subscriptions",
    "azure.list_management_groups",
    "azure.list_resources",
    "azure.query_resources",
    "azure.get_resource",
    "powerplatform.list_environments",
    "powerplatform.get_environment",
    "powerplatform.list_flows",
    "powerplatform.list_apps",
    "powerplatform.list_solutions",
    "powerplatform.list_connections",
    "mcp.plan_capability",
    "mcp.simulate_capability",
    "workspace.plan_script",
    "workspace.simulate_script",
})

DESTRUCTIVE_VERBS = (
    "delete", "remove", "destroy", "drop", "purge", "kill", "terminate",
    "execute", "run", "modify", "update", "create", "write", "set",
    "disable", "enable", "restart", "stop", "start", "deploy", "grant",
    "revoke", "reset", "assign", "move", "copy", "publish",
)


class ControlledOperationsService:
    """Classify, plan, approve and simulate read-only cloud operations."""

    def __init__(
        self,
        *,
        approval_secret: bytes | None = None,
        now: Any = None,
    ) -> None:
        self._secret = approval_secret or secrets.token_bytes(32)
        self._now = now or time.time
        self._consumed_tokens: set[str] = set()
        self._token_lock = threading.Lock()

    # -- validation / classification ---------------------------------------

    @staticmethod
    def _validate(request: OperationRequest) -> OperationRequest:
        operation = str(request.operation or "").strip().lower()
        provider = str(request.provider or "").strip().lower()
        target = str(request.target or "").strip()
        if not _OPERATION_PATTERN.fullmatch(operation):
            raise ControlledOperationsError("Operation name is invalid.")
        if provider not in _PROVIDERS:
            raise ControlledOperationsError("Operation provider is invalid.")
        if (
            not target
            or len(target) > 2048
            or ".." in target
            or "//" in target
            or any(ord(char) < 32 for char in target)
        ):
            raise ControlledOperationsError("Operation target is invalid.")
        return OperationRequest(
            operation=operation,
            provider=provider,
            target=target,
            profile_id=request.profile_id,
            parameters=dict(request.parameters or {}),
        )

    def classify(self, request: OperationRequest) -> OperationRisk:
        clean = self._validate(request)
        if clean.operation in READ_ONLY_OPERATIONS:
            return OperationRisk.READ_ONLY
        tokens = set(clean.operation.split("."))
        if any(verb in tokens for verb in DESTRUCTIVE_VERBS) or any(
            verb in clean.operation for verb in DESTRUCTIVE_VERBS
        ):
            return OperationRisk.DESTRUCTIVE
        return OperationRisk.REVERSIBLE

    # -- plan / approval ----------------------------------------------------

    @staticmethod
    def _fingerprint(plan: dict[str, Any]) -> str:
        request = plan.get("request") if isinstance(plan, dict) else None
        if not isinstance(request, dict):
            raise ControlledOperationsError("Operation plan is malformed.")
        canonical = {
            "operation": str(request.get("operation") or ""),
            "provider": str(request.get("provider") or ""),
            "target": str(request.get("target") or ""),
            "profile_id": request.get("profile_id"),
            "parameters": request.get("parameters") or {},
        }
        payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def build_plan(self, request: OperationRequest) -> dict[str, Any]:
        clean = self._validate(request)
        risk = self.classify(clean)
        fingerprint = self._fingerprint({"request": clean.__dict__})
        if risk is OperationRisk.READ_ONLY:
            steps = ["validate_profile", "acquire_token", "perform_read", "redact_results"]
            permitted = True
        elif risk is OperationRisk.REVERSIBLE:
            steps = ["validate_profile", "require_approval", "simulate_only"]
            permitted = False
        else:
            steps = ["blocked_by_policy"]
            permitted = False
        return {
            "plan_id": fingerprint[:16],
            "request": dict(clean.__dict__),
            "risk": risk.value,
            "steps": steps,
            "execution_permitted": permitted,
            "approved": False,
            "approval_token": None,
            "token_material_returned": False,
        }

    def request_approval(
        self,
        plan: dict[str, Any],
        *,
        approver: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> dict[str, Any]:
        if not isinstance(plan, dict):
            raise ControlledOperationsError("Operation plan is malformed.")
        if plan.get("risk") == OperationRisk.DESTRUCTIVE.value:
            raise ControlledOperationsError(
                "Destructive operations cannot be approved in this read-only build."
            )
        if plan.get("risk") == OperationRisk.READ_ONLY.value:
            raise ControlledOperationsError(
                "Read-only operations do not require approval; simulate them directly."
            )
        approver_clean = str(approver or "").strip()[:200]
        if not approver_clean:
            raise ControlledOperationsError("An approver identity is required.")
        ttl = int(ttl_seconds)
        if ttl <= 0 or ttl > 86400:
            raise ControlledOperationsError("Approval lifetime is invalid.")
        expiry = int(self._now()) + ttl
        signature = self._sign(self._fingerprint(plan), approver_clean, expiry)
        return {
            **plan,
            "approved": True,
            "approval_token": f"{signature}.{expiry}",
            "approval_expires_at": expiry,
            "approver": approver_clean,
        }

    def _sign(self, fingerprint: str, approver: str, expiry: int) -> str:
        message = f"{fingerprint}|{approver}|{expiry}".encode("utf-8")
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def verify_approval(
        self,
        plan: dict[str, Any],
        token: str,
        *,
        approver: str,
    ) -> bool:
        raw = str(token or "")
        approver_clean = str(approver or "").strip()[:200]
        if "." not in raw or not plan.get("approved"):
            return False
        if plan.get("risk") in (
            OperationRisk.DESTRUCTIVE.value,
            OperationRisk.READ_ONLY.value,
        ):
            return False
        signature, _, expiry_text = raw.rpartition(".")
        try:
            expiry = int(expiry_text)
        except (TypeError, ValueError):
            return False
        if expiry <= int(self._now()):
            return False
        expected = self._sign(self._fingerprint(plan), approver_clean, expiry)
        if not hmac.compare_digest(signature, expected):
            return False
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        with self._token_lock:
            if digest in self._consumed_tokens:
                return False
            self._consumed_tokens.add(digest)
        return True

    def simulate(
        self,
        plan: dict[str, Any],
        token: str,
        *,
        approver: str,
    ) -> dict[str, Any]:
        if plan.get("risk") == OperationRisk.DESTRUCTIVE.value:
            return {
                "success": False,
                "enabled": False,
                "error": "Destructive operations are blocked by policy.",
            }
        if plan.get("risk") != OperationRisk.READ_ONLY.value and not self.verify_approval(
            plan, token, approver=approver
        ):
            return {
                "success": False,
                "enabled": False,
                "error": "Approval is missing, expired or invalid.",
            }
        return {
            "success": True,
            "simulated": True,
            "executed": False,
            "plan_id": plan.get("plan_id"),
            "steps": [
                {"step": step, "seq": index, "simulated": True}
                for index, step in enumerate(plan.get("steps", []), start=1)
            ],
            "token_material_returned": False,
        }

    def execute(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Always refuses. Execution belongs to a separately approved runner."""
        return {
            "success": False,
            "enabled": False,
            "error": (
                "Execution is not enabled in this read-only build. "
                "Use an externally approved runner with its own audit trail."
            ),
        }

    @staticmethod
    def describe_policy() -> dict[str, Any]:
        return {
            "read_only_operations": sorted(READ_ONLY_OPERATIONS),
            "destructive_verbs": list(DESTRUCTIVE_VERBS),
            "execution_enabled": False,
            "approval_token_binding": "hmac_sha256_plan_approver_expiry",
        }
