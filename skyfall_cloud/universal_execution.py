"""Universal execution engine (plan-only, read-only slice).

This module resolves capabilities, classifies failures, builds plans, performs
bounded dry-run simulation and records verification outcomes. It deliberately
does not execute code or cloud mutations: there is no subprocess/process
runner, no network access, no credential handling, no database writes and no
source-content reads.

Safety invariants:
- MCP/registry resolution is attempted first; workspace fallback is only used
  when explicitly requested and only through AI-metadata-safe workspace APIs.
- Workspace AI metadata consent is not execution authorization.
- Failure classification is informational, never authorization.
- Public outputs are redacted and bounded; tokens/secrets/absolute paths,
  stdout/stderr, raw command lines and source content are never exposed.
- Simulation sets executed=False and produces planned steps only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from skyfall_mcp.registry import Capability, CapabilityRegistry

try:
    from skyfall_cloud.cloud_orchestration import redact_error_text as _shared_redact_error_text
except Exception:  # pragma: no cover - defensive import fallback
    _shared_redact_error_text = None

_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-+/=]{8,}", re.IGNORECASE)
_LONG_SECRET_RE = re.compile(r"\beyJ[A-Za-z0-9._\-]{12,}|\b[A-Za-z0-9]{40,}={0,2}\b")
_KV_SECRET_RE = re.compile(
    r"(?i)\b(access[_-]?token|refresh[_-]?token|id[_-]?token|client[_-]?secret|password|passwd|secret|api[_-]?key|authorization|token)\b\s*[:=]\s*([^\s,;\"']+)"
)
_WINDOWS_PATH_RE = re.compile(
    r"(?:\b[A-Za-z]:\\[^\s\"'<>|]+|\b[A-Za-z]:/[^\s\"'<>|]+|\\\\[^\s\"'<>|]+)"
)
_UNIX_PATH_RE = re.compile(r"(?<!\w)/(?:[^\s\"'<>|]+)")
_SECRET_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "client_secret",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "key",
}
_SENSITIVE_OUTPUT_KEYS = {"stdout", "stderr", "command", "cmd", "command_line", "argv", "source", "content"}


class FailureType(str, Enum):
    NONE = "none"
    CAPABILITY_NOT_FOUND = "capability_not_found"
    CAPABILITY_DISABLED = "capability_disabled"
    CONSENT_REVOKED = "consent_revoked"
    WORKSPACE_FALLBACK_NOT_ALLOWED = "workspace_fallback_not_allowed"
    WORKSPACE_RESOURCE_NOT_FOUND = "workspace_resource_not_found"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_INVALID = "approval_invalid"
    VERIFICATION_FAILED = "verification_failed"
    POLICY_BLOCKED = "policy_blocked"
    INVALID_REQUEST = "invalid_request"
    INTERNAL_ERROR = "internal_error"


class ExecutionMode(str, Enum):
    DRY_RUN = "dry_run"


class PlanStatus(str, Enum):
    RESOLVED = "resolved"
    PLANNED = "planned"
    REJECTED = "rejected"


class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    BOUND = "bound"
    INVALID = "invalid"


class SimulationStatus(str, Enum):
    NOT_RUN = "not_run"
    SIMULATED = "simulated"
    FAILED = "failed"


class VerificationStatus(str, Enum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class ExecutionRequest:
    operation: str = ""
    tool_name: str = ""
    capability_id: str = ""
    provider: str = ""
    target: str = ""
    profile_id: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    mode: ExecutionMode = ExecutionMode.DRY_RUN
    allow_workspace_fallback: bool = False
    workspace_id: str | None = None
    file_id: str | None = None
    query: str | None = None
    approval_token: str | None = None
    approver: str | None = None
    requires_mutation: bool = False


@dataclass(frozen=True)
class CapabilityResolution:
    source: str
    resolved: bool
    capability_id: str | None = None
    tool_name: str | None = None
    operation: str | None = None
    provider: str | None = None
    target: str | None = None
    workspace_id: str | None = None
    file_id: str | None = None
    file_name: str | None = None
    relative_path: str | None = None
    file_type: str | None = None
    failure_type: FailureType = FailureType.NONE
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "resolved": self.resolved,
            "capability_id": redact_public_text(self.capability_id) if self.capability_id else None,
            "tool_name": redact_public_text(self.tool_name) if self.tool_name else None,
            "operation": redact_public_text(self.operation) if self.operation else None,
            "provider": redact_public_text(self.provider) if self.provider else None,
            "target": redact_public_text(self.target) if self.target else None,
            "workspace_id": redact_public_text(self.workspace_id) if self.workspace_id else None,
            "file_id": redact_public_text(self.file_id) if self.file_id else None,
            "file_name": redact_public_text(self.file_name) if self.file_name else None,
            "relative_path": redact_public_text(self.relative_path) if self.relative_path else None,
            "file_type": redact_public_text(self.file_type) if self.file_type else None,
            "failure_type": self.failure_type.value,
            "message": redact_public_text(self.message),
            "metadata": _sanitize_public_value(self.metadata),
        }


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    passed: bool
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": redact_public_text(self.message),
        }


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    checks: tuple[VerificationCheck, ...] = ()
    failure_type: FailureType = FailureType.NONE

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "checks": [check.to_dict() for check in self.checks],
            "failure_type": self.failure_type.value,
            "passed": self.status == VerificationStatus.PASSED,
        }


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    request_id: str
    status: PlanStatus
    mode: ExecutionMode
    approval_status: ApprovalStatus
    approval_required: bool
    approval_fingerprint: str | None
    steps: tuple[dict[str, Any], ...]
    resolution: CapabilityResolution
    failure_type: FailureType = FailureType.NONE
    message: str = ""
    mutable: bool = False
    parameters: dict[str, Any] = field(default_factory=dict)
    profile_id: str | None = None
    requires_mutation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "request_id": self.request_id,
            "status": self.status.value,
            "mode": self.mode.value,
            "approval_status": self.approval_status.value,
            "approval_required": self.approval_required,
            "approval_bound": self.approval_status == ApprovalStatus.BOUND,
            "mutable": self.mutable,
            "steps": [_sanitize_public_value(step) for step in self.steps],
            "resolution": self.resolution.to_dict(),
            "failure_type": self.failure_type.value,
            "message": redact_public_text(self.message),
            "executed": False,
            "process_started": False,
        }


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    executed: bool
    simulated: bool
    steps: tuple[dict[str, Any], ...]
    verification: VerificationResult
    failure_type: FailureType = FailureType.NONE
    message: str = ""
    process_started: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "executed": self.executed,
            "simulated": self.simulated,
            "process_started": self.process_started,
            "steps": [_sanitize_public_value(step) for step in self.steps],
            "verification": self.verification.to_dict(),
            "failure_type": self.failure_type.value,
            "message": redact_public_text(self.message),
        }


@dataclass(frozen=True)
class ExecutionRecord:
    record_id: str
    request_id: str
    created_at: float
    resolution: CapabilityResolution
    plan: ExecutionPlan | None
    result: ExecutionResult | None
    failure_type: FailureType = FailureType.NONE

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "request_id": self.request_id,
            "created_at": self.created_at,
            "resolution": self.resolution.to_dict(),
            "plan": self.plan.to_dict() if self.plan else None,
            "result": self.result.to_dict() if self.result else None,
            "failure_type": self.failure_type.value,
        }


class ExecutionHistory:
    """Bounded in-memory execution history."""

    def __init__(self, limit: int = 50) -> None:
        self._limit = max(1, int(limit))
        self._records: deque[ExecutionRecord] = deque(maxlen=self._limit)
        self._lock = threading.Lock()

    def add(self, record: ExecutionRecord) -> None:
        with self._lock:
            self._records.append(record)

    def get(self, record_id: str) -> ExecutionRecord | None:
        clean = str(record_id or "").strip()
        with self._lock:
            for record in reversed(self._records):
                if record.record_id == clean or record.request_id == clean:
                    return record
        return None

    def list(self, limit: int | None = None) -> list[ExecutionRecord]:
        with self._lock:
            items = list(self._records)
        if limit is not None:
            items = items[-max(0, int(limit)) :]
        return list(reversed(items))

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


def redact_public_text(value: Any, *, limit: int = 300) -> str:
    if _shared_redact_error_text is not None:
        try:
            return _shared_redact_error_text(value, limit=limit)
        except TypeError:
            pass
    text = str(value or "")
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _LONG_SECRET_RE.sub("[REDACTED]", text)
    text = _KV_SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    text = _WINDOWS_PATH_RE.sub("[REDACTED_PATH]", text)
    text = _UNIX_PATH_RE.sub("[REDACTED_PATH]", text)
    return text[: max(0, int(limit))]


def _sanitize_public_value(value: Any, *, key: str | None = None) -> Any:
    if key and key.lower() in _SECRET_KEYS:
        return "[REDACTED]"
    if key and key.lower() in _SENSITIVE_OUTPUT_KEYS:
        return "[REDACTED]"
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for item_key, item_value in value.items():
            clean_key = str(item_key)
            if clean_key.lower() in _SENSITIVE_OUTPUT_KEYS:
                sanitized[clean_key] = "[REDACTED]"
            else:
                sanitized[clean_key] = _sanitize_public_value(item_value, key=clean_key)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [_sanitize_public_value(item) for item in value]
    if isinstance(value, (str, bytes)):
        return redact_public_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_public_text(value)


class UniversalExecutionEngine:
    """Plan-only universal execution engine."""

    def __init__(
        self,
        *,
        registry: CapabilityRegistry | None = None,
        workspace_manager: Any = None,
        approval_secret: bytes | None = None,
        history_limit: int = 50,
        now: Any = None,
    ) -> None:
        self._registry = registry or CapabilityRegistry.default()
        self._workspace_manager = workspace_manager
        self._approval_secret = approval_secret or secrets.token_bytes(32)
        self._history = ExecutionHistory(limit=history_limit)
        self._consumed_approvals: set[str] = set()
        self._approval_lock = threading.Lock()
        self._now = now or time.time

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _clean_request(request: ExecutionRequest) -> ExecutionRequest:
        params = request.parameters if isinstance(request.parameters, dict) else {}
        return ExecutionRequest(
            operation=str(request.operation or "").strip(),
            tool_name=str(request.tool_name or "").strip(),
            capability_id=str(request.capability_id or "").strip(),
            provider=str(request.provider or "").strip().lower(),
            target=str(request.target or "").strip(),
            profile_id=(str(request.profile_id).strip() if request.profile_id is not None else None),
            parameters=dict(params),
            mode=request.mode if isinstance(request.mode, ExecutionMode) else ExecutionMode.DRY_RUN,
            allow_workspace_fallback=bool(request.allow_workspace_fallback),
            workspace_id=(str(request.workspace_id).strip() if request.workspace_id is not None else None),
            file_id=(str(request.file_id).strip() if request.file_id is not None else None),
            query=(str(request.query).strip() if request.query is not None else None),
            approval_token=(str(request.approval_token).strip() if request.approval_token is not None else None),
            approver=(str(request.approver).strip() if request.approver is not None else None),
            requires_mutation=bool(request.requires_mutation),
        )

    def classify_failure(self, value: Any) -> FailureType:
        if value is None:
            return FailureType.NONE
        if isinstance(value, FailureType):
            return value
        text = str(value or "").strip().lower()
        mapping = {
            "capability_not_found": FailureType.CAPABILITY_NOT_FOUND,
            "not_found": FailureType.CAPABILITY_NOT_FOUND,
            "capability_disabled": FailureType.CAPABILITY_DISABLED,
            "disabled": FailureType.CAPABILITY_DISABLED,
            "consent_revoked": FailureType.CONSENT_REVOKED,
            "consent": FailureType.CONSENT_REVOKED,
            "workspace_fallback_not_allowed": FailureType.WORKSPACE_FALLBACK_NOT_ALLOWED,
            "fallback_not_allowed": FailureType.WORKSPACE_FALLBACK_NOT_ALLOWED,
            "workspace_resource_not_found": FailureType.WORKSPACE_RESOURCE_NOT_FOUND,
            "approval_required": FailureType.APPROVAL_REQUIRED,
            "approval_invalid": FailureType.APPROVAL_INVALID,
            "verification_failed": FailureType.VERIFICATION_FAILED,
            "policy_blocked": FailureType.POLICY_BLOCKED,
            "invalid_request": FailureType.INVALID_REQUEST,
        }
        for key, failure in mapping.items():
            if key == text or key in text:
                return failure
        return FailureType.INTERNAL_ERROR if text else FailureType.NONE

    def _resolve_mcp(self, request: ExecutionRequest) -> CapabilityResolution | None:
        capability: Capability | None = None
        for candidate_id in (request.capability_id, request.operation):
            if not candidate_id:
                continue
            try:
                candidate = self._registry.get(candidate_id)
            except Exception:
                candidate = None
            if candidate is not None and candidate.status == "enabled" and candidate.execution_enabled:
                capability = candidate
                break
        if capability is None and request.tool_name and hasattr(self._registry, "find_by_tool_name"):
            capability = self._registry.find_by_tool_name(request.tool_name)
        if capability is None and request.operation and hasattr(self._registry, "find_by_operation"):
            capability = self._registry.find_by_operation(request.operation)
        if capability is None:
            return None
        provider = request.provider or capability.category
        operation = request.operation or capability.id
        return CapabilityResolution(
            source="mcp",
            resolved=True,
            capability_id=capability.id,
            tool_name=capability.tool_name,
            operation=operation,
            provider=provider,
            target=request.target or capability.tool_name,
            failure_type=FailureType.NONE,
            message="Resolved via MCP capability registry.",
            metadata={"category": capability.category, "risk": capability.risk},
        )

    @staticmethod
    def _workspace_relative_path(payload: Mapping[str, Any]) -> str | None:
        for key in ("relative_path", "relativePath", "path_relative", "pathRelative"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                clean = value.strip().replace("\\", "/").lstrip("/")
                return clean[:500]
        path = payload.get("path")
        name = payload.get("name") or payload.get("file_name")
        if isinstance(path, str) and isinstance(name, str) and path.endswith(name):
            return name[:500]
        if isinstance(name, str) and name.strip():
            return name.strip()[:500]
        return None

    def _resolve_workspace_fallback(self, request: ExecutionRequest) -> CapabilityResolution:
        if not request.allow_workspace_fallback:
            return CapabilityResolution(
                source="workspace",
                resolved=False,
                operation=request.operation or "workspace.resolve",
                provider="workspace",
                target=request.target or request.file_id or (request.query or ""),
                failure_type=FailureType.WORKSPACE_FALLBACK_NOT_ALLOWED,
                message="Workspace fallback was not explicitly requested.",
            )
        manager = self._workspace_manager
        if manager is None:
            return CapabilityResolution(
                source="workspace",
                resolved=False,
                operation=request.operation or "workspace.resolve",
                provider="workspace",
                target=request.target or request.file_id or (request.query or ""),
                failure_type=FailureType.CONSENT_REVOKED,
                message="Workspace AI metadata access is not available.",
            )
        file_payload: Mapping[str, Any] | None = None
        try:
            if request.file_id and hasattr(manager, "describe_file_for_ai"):
                try:
                    result = manager.describe_file_for_ai(request.file_id)
                except (KeyError, ValueError) as exc:
                    reason = str(exc).lower()
                    if any(
                        token in reason
                        for token in ("consent", "sharing is not enabled", "not shared", "permission")
                    ):
                        failure = FailureType.CONSENT_REVOKED
                    else:
                        failure = FailureType.WORKSPACE_RESOURCE_NOT_FOUND
                    return CapabilityResolution(
                        source="workspace",
                        resolved=False,
                        operation=request.operation or "workspace.describe_file",
                        provider="workspace",
                        target=request.file_id or "",
                        workspace_id=request.workspace_id,
                        failure_type=failure,
                        message="Workspace AI metadata could not describe that file.",
                    )
                if isinstance(result, dict):
                    if result.get("success") is True and isinstance(result.get("file"), dict):
                        file_payload = result["file"]
                    elif result.get("file_id") or result.get("relative_path") or result.get("name"):
                        # WorkspaceManager.describe_file_for_ai returns a flat file dict.
                        file_payload = result
                    else:
                        error = str(result.get("error") or "").lower()
                        if "consent" in error or "sharing is not enabled" in error or "not shared" in error or "permission" in error:
                            return CapabilityResolution(
                                source="workspace",
                                resolved=False,
                                operation=request.operation or "workspace.describe_file",
                                provider="workspace",
                                target=request.file_id or "",
                                workspace_id=request.workspace_id,
                                failure_type=FailureType.CONSENT_REVOKED,
                                message="Workspace AI metadata consent is not available.",
                            )
            if file_payload is None and request.query and hasattr(manager, "search_for_ai"):
                results = manager.search_for_ai(request.query, workspace_id=request.workspace_id)
                if isinstance(results, list) and results:
                    first = results[0]
                    if isinstance(first, dict):
                        file_payload = first
                elif request.workspace_id and hasattr(manager, "get_workspace"):
                    ws = manager.get_workspace(request.workspace_id)
                    allow_ai = bool(getattr(ws, "allow_ai_metadata", False)) if ws else False
                    if not allow_ai:
                        return CapabilityResolution(
                            source="workspace",
                            resolved=False,
                            operation=request.operation or "workspace.search_files",
                            provider="workspace",
                            target=request.query or "",
                            workspace_id=request.workspace_id,
                            failure_type=FailureType.CONSENT_REVOKED,
                            message="Workspace AI metadata consent is not available.",
                        )
        except Exception as exc:  # noqa: BLE001 - reported as safe resolution failure
            failure = self.classify_failure(exc)
            if failure in (FailureType.NONE, FailureType.INTERNAL_ERROR):
                failure = FailureType.WORKSPACE_RESOURCE_NOT_FOUND
            return CapabilityResolution(
                source="workspace",
                resolved=False,
                operation=request.operation or "workspace.resolve",
                provider="workspace",
                target=request.file_id or request.query or request.target,
                workspace_id=request.workspace_id,
                failure_type=failure,
                message="Workspace fallback could not resolve safe metadata.",
            )
        if not isinstance(file_payload, dict):
            return CapabilityResolution(
                source="workspace",
                resolved=False,
                operation=request.operation or "workspace.resolve",
                provider="workspace",
                target=request.file_id or request.query or request.target,
                workspace_id=request.workspace_id,
                failure_type=FailureType.WORKSPACE_RESOURCE_NOT_FOUND,
                message="No approved workspace metadata matched the request.",
            )
        workspace_id = str(file_payload.get("workspace_id") or request.workspace_id or "").strip() or None
        file_id = str(file_payload.get("file_id") or request.file_id or "").strip() or None
        file_name = str(file_payload.get("name") or file_payload.get("file_name") or "").strip() or None
        relative_path = self._workspace_relative_path(file_payload)
        file_type = str(file_payload.get("file_type") or file_payload.get("type") or "").strip() or None
        op = request.operation or "workspace.plan_script"
        return CapabilityResolution(
            source="workspace",
            resolved=True,
            capability_id=None,
            tool_name=None,
            operation=op,
            provider="workspace",
            target=file_id or relative_path or file_name or op,
            workspace_id=workspace_id,
            file_id=file_id,
            file_name=file_name,
            relative_path=relative_path,
            file_type=file_type,
            failure_type=FailureType.NONE,
            message="Resolved via approved workspace metadata only.",
            metadata={
                key: value
                for key, value in {
                    "workspace_id": workspace_id,
                    "file_id": file_id,
                    "relative_path": relative_path,
                    "file_type": file_type,
                }.items()
                if value
            },
        )

    def resolve(self, request: ExecutionRequest) -> CapabilityResolution:
        clean = self._clean_request(request)
        if clean.mode != ExecutionMode.DRY_RUN:
            return CapabilityResolution(
                source="none",
                resolved=False,
                operation=clean.operation or clean.tool_name or clean.capability_id,
                provider=clean.provider or None,
                target=clean.target or None,
                failure_type=FailureType.POLICY_BLOCKED,
                message="Only dry-run planning is permitted.",
            )
        if not (clean.operation or clean.tool_name or clean.capability_id or clean.file_id or clean.query):
            return CapabilityResolution(
                source="none",
                resolved=False,
                failure_type=FailureType.INVALID_REQUEST,
                message="A capability identifier or explicit workspace fallback target is required.",
            )
        mcp = self._resolve_mcp(clean)
        if mcp is not None:
            return mcp
        # MCP-first failed; only then consider explicit workspace fallback.
        if clean.allow_workspace_fallback or clean.file_id or clean.workspace_id or clean.query:
            return self._resolve_workspace_fallback(clean)
        operation = clean.operation or clean.tool_name or clean.capability_id
        failure = FailureType.CAPABILITY_DISABLED
        try:
            for cid in (clean.capability_id, clean.operation):
                if cid:
                    cap = self._registry.get(cid)
                    if cap.status != "enabled" or not cap.execution_enabled:
                        failure = FailureType.CAPABILITY_DISABLED
                        break
            else:
                failure = FailureType.CAPABILITY_NOT_FOUND
        except Exception:
            failure = FailureType.CAPABILITY_NOT_FOUND
        return CapabilityResolution(
            source="mcp",
            resolved=False,
            operation=operation,
            provider=clean.provider or None,
            target=clean.target or operation,
            failure_type=failure,
            message="No enabled MCP capability matched the request.",
        )

    def _approval_fingerprint(self, plan: ExecutionPlan) -> str:
        canonical_payload = {
            "plan_id": plan.plan_id,
            "request_id": plan.request_id,
            "status": plan.status.value,
            "mode": plan.mode.value,
            "mutable": plan.mutable,
            "approval_required": plan.approval_required,
            "requires_mutation": plan.requires_mutation,
            "profile_id": plan.profile_id,
            "steps": [_sanitize_public_value(step) for step in plan.steps],
            "parameters": _sanitize_public_value(plan.parameters),
            "resolution": {
                "capability_id": plan.resolution.capability_id,
                "tool_name": plan.resolution.tool_name,
                "operation": plan.resolution.operation,
                "provider": plan.resolution.provider,
                "target": plan.resolution.target,
                "workspace_id": plan.resolution.workspace_id,
                "file_id": plan.resolution.file_id,
                "relative_path": plan.resolution.relative_path,
            },
        }
        canonical = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _bind_approval(self, plan: ExecutionPlan, token: str | None, approver: str | None) -> ApprovalStatus:
        if not plan.mutable:
            return ApprovalStatus.NOT_REQUIRED
        if not token or not approver:
            return ApprovalStatus.REQUIRED
        raw = str(token)
        if "." not in raw:
            return ApprovalStatus.INVALID
        signature, _, expiry_text = raw.rpartition(".")
        try:
            expiry = int(expiry_text)
        except (TypeError, ValueError):
            return ApprovalStatus.INVALID
        if expiry <= int(self._now()):
            return ApprovalStatus.INVALID
        fingerprint = self._approval_fingerprint(plan)
        expected = hmac.new(
            self._approval_secret,
            f"{fingerprint}|{approver.strip()}|{expiry}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return ApprovalStatus.INVALID
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        with self._approval_lock:
            if digest in self._consumed_approvals:
                return ApprovalStatus.INVALID
            self._consumed_approvals.add(digest)
        return ApprovalStatus.BOUND

    def issue_plan_approval(self, plan: ExecutionPlan, approver: str, ttl_seconds: int = 900) -> str:
        """Issue an HMAC approval token bound to the full immutable plan. For engine-internal/test use."""
        if not plan.mutable:
            raise ValueError("Approval is not required for non-mutating plans.")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive.")
        fingerprint = self._approval_fingerprint(plan)
        expiry = int(self._now()) + int(ttl_seconds)
        signature = hmac.new(
            self._approval_secret,
            f"{fingerprint}|{approver.strip()}|{expiry}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{signature}.{expiry}"

    def _is_mutating(self, request: ExecutionRequest, resolution: CapabilityResolution) -> bool:
        if request.requires_mutation:
            return True
        op = (resolution.operation or request.operation or "").lower()
        tool = (resolution.tool_name or request.tool_name or "").lower()
        mutating_tokens = (
            "create", "update", "delete", "remove", "write", "set", "start", "stop",
            "restart", "deploy", "execute", "run", "modify", "grant", "revoke",
        )
        # plan/simulate/get/list/describe/discover/inventory are read-only by intent.
        if any(op.startswith(prefix) or op.endswith(prefix) for prefix in ("get_", "list_", "describe_", "discover_", "inventory_", "search_", "route_", "build_", "correlate_", "plan_", "simulate_")):
            return False
        if tool.startswith(("get_", "list_", "describe_", "discover_", "inventory_", "search_", "route_", "build_", "correlate_", "plan_")):
            return False
        return any(token in op.split(".") or token in op.split("_") or token in tool.split("_") for token in mutating_tokens)

    def plan(self, request: ExecutionRequest) -> tuple[CapabilityResolution, ExecutionPlan, ExecutionRecord]:
        clean = self._clean_request(request)
        request_id = self._new_id("req")
        resolution = self.resolve(clean)
        mutable = self._is_mutating(clean, resolution) if resolution.resolved else bool(clean.requires_mutation)
        approval_status = ApprovalStatus.NOT_REQUIRED
        failure_type = resolution.failure_type
        status = PlanStatus.PLANNED if resolution.resolved else PlanStatus.REJECTED
        message = resolution.message or ("Plan created." if resolution.resolved else "Resolution failed.")
        steps: list[dict[str, Any]] = []
        if resolution.resolved:
            steps = [
                {"step": "resolve_capability", "status": "completed", "source": resolution.source},
                {"step": "classify_risk", "status": "completed", "mutable": mutable},
                {"step": "build_dry_run_plan", "status": "completed", "mode": ExecutionMode.DRY_RUN.value},
                {"step": "simulate_without_execution", "status": "pending", "executed": False},
                {"step": "verify_plan_outputs", "status": "pending"},
            ]
            if mutable:
                approval_status = ApprovalStatus.REQUIRED
                steps.insert(3, {"step": "require_approval_binding", "status": "pending"})
                message = "Plan created for a mutating request; approval binding is required before simulation."
        else:
            steps = [{"step": "resolve_capability", "status": "failed", "failure_type": failure_type.value}]
        plan = ExecutionPlan(
            plan_id=self._new_id("plan"),
            request_id=request_id,
            status=status,
            mode=ExecutionMode.DRY_RUN,
            approval_status=approval_status,
            approval_required=mutable and resolution.resolved,
            approval_fingerprint=None,
            steps=tuple(steps),
            resolution=resolution,
            failure_type=failure_type,
            message=message,
            mutable=mutable and resolution.resolved,
            parameters=dict(clean.parameters),
            profile_id=clean.profile_id,
            requires_mutation=bool(clean.requires_mutation),
        )
        record = ExecutionRecord(
            record_id=self._new_id("record"),
            request_id=request_id,
            created_at=float(self._now()),
            resolution=resolution,
            plan=plan,
            result=None,
            failure_type=failure_type,
        )
        self._history.add(record)
        return resolution, plan, record

    def verify(self, plan: ExecutionPlan, result: ExecutionResult | None = None) -> VerificationResult:
        checks: list[VerificationCheck] = []
        checks.append(VerificationCheck("plan_resolved", plan.resolution.resolved and plan.status == PlanStatus.PLANNED,
                                        "Plan must be resolved before simulation."))
        checks.append(VerificationCheck("dry_run_mode", plan.mode == ExecutionMode.DRY_RUN,
                                        "Only dry-run mode is permitted."))
        process_started = bool(getattr(result, "process_started", False)) if result is not None else False
        checks.append(VerificationCheck("no_process_started", not process_started, "No process was started."))
        if result is not None:
            checks.append(VerificationCheck("result_not_executed", result.executed is False,
                                            "Simulation must not execute actions."))
            checks.append(VerificationCheck("result_steps_only", isinstance(result.steps, tuple),
                                            "Simulation must produce steps only."))
        if plan.mutable:
            checks.append(VerificationCheck("approval_bound", plan.approval_status == ApprovalStatus.BOUND,
                                            "Mutating plans require approval binding before simulation."))
        passed = all(check.passed for check in checks)
        return VerificationResult(
            status=VerificationStatus.PASSED if passed else VerificationStatus.FAILED,
            checks=tuple(checks),
            failure_type=FailureType.NONE if passed else FailureType.VERIFICATION_FAILED,
        )

    def simulate(self, plan: ExecutionPlan, *, approval_token: str | None = None, approver: str | None = None) -> tuple[ExecutionResult, ExecutionRecord]:
        bound_status = self._bind_approval(plan, approval_token, approver)
        effective_plan = plan
        if plan.mutable:
            effective_plan = ExecutionPlan(
                plan_id=plan.plan_id,
                request_id=plan.request_id,
                status=plan.status,
                mode=plan.mode,
                approval_status=bound_status,
                approval_required=plan.approval_required,
                approval_fingerprint=plan.approval_fingerprint,
                steps=plan.steps,
                resolution=plan.resolution,
                failure_type=plan.failure_type,
                message=plan.message,
                mutable=plan.mutable,
                parameters=dict(plan.parameters),
                profile_id=plan.profile_id,
                requires_mutation=plan.requires_mutation,
            )
        if not plan.resolution.resolved or plan.status != PlanStatus.PLANNED:
            result = ExecutionResult(
                success=False,
                executed=False,
                simulated=False,
                steps=tuple(),
                verification=VerificationResult(VerificationStatus.FAILED, failure_type=FailureType.VERIFICATION_FAILED),
                failure_type=plan.failure_type or FailureType.VERIFICATION_FAILED,
                message="Cannot simulate an unresolved or rejected plan.",
            )
        elif plan.mutable and bound_status != ApprovalStatus.BOUND:
            failure = FailureType.APPROVAL_REQUIRED if bound_status == ApprovalStatus.REQUIRED else FailureType.APPROVAL_INVALID
            result = ExecutionResult(
                success=False,
                executed=False,
                simulated=False,
                steps=tuple({"step": "require_approval_binding", "status": "failed", "failure_type": failure.value},),
                verification=VerificationResult(
                    VerificationStatus.FAILED,
                    checks=(VerificationCheck("approval_bound", False, "Approval binding missing or invalid."),),
                    failure_type=FailureType.VERIFICATION_FAILED,
                ),
                failure_type=failure,
                message="Approval binding is required for mutating plans.",
            )
        else:
            sim_steps = tuple(
                {
                    **_sanitize_public_value(step),
                    "simulated": True,
                    "executed": False,
                }
                for step in plan.steps
            )
            provisional = ExecutionResult(
                success=True,
                executed=False,
                simulated=True,
                steps=sim_steps,
                verification=VerificationResult(VerificationStatus.NOT_RUN),
                failure_type=FailureType.NONE,
                message="Dry-run simulation completed. No process was started.",
            )
            verification = self.verify(effective_plan, provisional)
            success = verification.status == VerificationStatus.PASSED
            result = ExecutionResult(
                success=success,
                executed=False,
                simulated=True,
                steps=sim_steps,
                verification=verification,
                failure_type=FailureType.NONE if success else FailureType.VERIFICATION_FAILED,
                message=provisional.message if success else "Simulation verification failed.",
            )
        existing = self.get_record(plan.request_id)
        record = ExecutionRecord(
            record_id=existing.record_id if existing else self._new_id("record"),
            request_id=plan.request_id,
            created_at=existing.created_at if existing else float(self._now()),
            resolution=plan.resolution,
            plan=effective_plan,
            result=result,
            failure_type=result.failure_type,
        )
        self._history.add(record)
        return result, record

    def get_record(self, record_id: str) -> ExecutionRecord | None:
        return self._history.get(record_id)

    def list_history(self, limit: int | None = None) -> list[ExecutionRecord]:
        return self._history.list(limit=limit)


__all__ = [
    "ApprovalStatus",
    "CapabilityResolution",
    "ExecutionHistory",
    "ExecutionMode",
    "ExecutionPlan",
    "ExecutionRecord",
    "ExecutionRequest",
    "ExecutionResult",
    "FailureType",
    "PlanStatus",
    "SimulationStatus",
    "UniversalExecutionEngine",
    "VerificationCheck",
    "VerificationResult",
    "VerificationStatus",
    "redact_public_text",
]
