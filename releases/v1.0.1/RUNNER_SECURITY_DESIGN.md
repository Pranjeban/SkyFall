# Controlled Runner — Security Boundary Design (v1.0.1)

**Status:** Draft design (no code changes)
**Owner:** Security review
**Scope:** Approved workspace script execution (Python, PowerShell, Azure CLI, Microsoft Graph, Azure SDK, Power Platform API, internal automation, MCP tools).

## 1. Current state
- `execution/` package is effectively empty (no runner implementation).
- `skyfall_cloud/controlled_runner.py` is a stub; arbitrary workspace script execution remains disabled.
- `natural_language_orchestrator.py` and Execution Center preview only display script metadata; no source execution.
- `audits/audit_logger.py` exists but is not wired into an execution path.
- `skyfall_workspace/manager.py` provides workspace registration/discovery.

Conclusion: there is no execution boundary yet to harden. This document defines the required boundary before any runner is implemented.

## 2. Threat model
- Malicious or compromised approved workspace scripts.
- Prompt-injection via natural language causing unauthorized execution.
- Credential/token leakage through script stdout/stderr or artifacts.
- Destructive operations against production Azure/Power Platform resources.
- Path traversal / symlink attacks escaping approved workspaces.
- Dependency supply-chain attacks (pip modules, PowerShell modules).
- Long-running or resource-exhausting processes (DoS).
- Audit evasion (missing or tampered logs).

## 3. Required controls
1. **Workspace allowlist**: only explicitly registered workspaces; path canonicalization; reject symlinks escaping root; no arbitrary filesystem paths.
2. **Script allowlist & hashing**: index scripts with SHA-256; record hash at execution; detect tampering; only execute indexed scripts.
3. **Language/runtime allowlist**: Python (pinned interpreter), PowerShell (constrained language mode where feasible), Azure CLI, approved SDK calls. No shell=True; argument arrays only.
4. **Parameter validation**: typed schema per script; validate types/ranges; no raw shell interpolation.
5. **Environment resolution**: explicit tenant/subscription/environment selection; never infer production from defaults.
6. **Authentication context**: pass tokens via environment/SDK only; never print; redact in logs; short-lived tokens.
7. **Approval workflow**: risk classification (read-only / mutating / destructive); explicit user confirmation for mutating+; multi-step approval for destructive/production.
8. **Sandboxing**: subprocess with timeout, CPU/memory limits, no network by default (opt-in), working dir = workspace, env scrubbed (no secrets), stdout/stderr captured and size-capped.
9. **Production safeguards**: separate confirmation for production targets; block destructive ops in production unless explicitly approved.
10. **Audit logging**: execution ID, user identity, script hash, parameters (redacted), target, start/end, exit code, artifact hashes; append-only storage; tamper-evident (hash chain optional).
11. **Result validation**: verify expected artifacts; report failures; no silent success.
12. **Rollback guidance**: record pre-state where feasible; provide undo steps.

## 4. Recommended architecture
- A `ControlledRunner` service (FastAPI-local or in-process) owns execution.
- `WorkspaceManager` provides allowlisted roots and script index.
- `ScriptIndex` stores metadata + SHA-256.
- `ApprovalService` gates mutating/destructive runs.
- `AuditLogger` records every attempt (including denied).
- `SandboxExecutor` runs subprocess with limits and captures output.
- `ArtifactStore` stores results with metadata.
- Copilot/MCP/NI layer may *request* execution but never executes directly; must go through runner + approval.

## 5. Risks and open questions
- Python/PowerShell sandboxing on Windows is limited; consider job objects / Windows Sandbox for high-risk runs.
- Secret redaction in arbitrary script output is best-effort; prefer scripts that accept tokens via env and never echo them.
- Dependency pinning and vulnerability scanning for approved scripts.
- Whether to support interactive (TTY) scripts (recommend: no).
- Audit storage location and retention policy (local SQLite vs append-only file).
- Performance: concurrency limits and queueing.

## 6. Validation recommendations
- Unit tests for path canonicalization, hash verification, parameter validation, approval gating.
- Integration tests with a benign test script in a temp workspace.
- Security review of any future runner implementation before enabling.
- Keep arbitrary execution disabled until all controls implemented and reviewed.

## 7. Decision
Do not enable general script execution in v1.0.1 until the controlled runner, approval workflow, sandbox, and audit logging are implemented and security-reviewed. Continue shipping read-only inventory routes only.