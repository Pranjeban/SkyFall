# Security Audit — MCP Tools, Accounts, and Secret Handling (v1.0.1)

**Status:** Read-only audit, no code changes.
**Scope:** `skyfall_mcp/`, `skyfall_cloud/powerplatform_accounts.py`, `skyfall_cloud/azure_profiles.py`, `skyfall_cloud/azure_profile_manager.py`, `execution/command_runner.py`, `audits/audit_logger.py`.

## 1. Trust boundaries
- MCP server exposes read-only discovery/inventory tools; no write/execute tools registered for cloud resources.
- Controlled runner (`skyfall_cloud/controlled_runner.py`) is a stub; arbitrary execution remains disabled.
- Copilot/LLM layer may request capabilities but cannot bypass the runner or grant permissions.

## 2. Secret handling
- Tokens are never returned by inventory functions; responses include `secrets_returned: False` contract.
- Audit logger redacts via event fields only; ensure no token in stdout/stderr.
- Power Platform uses short-lived Azure CLI tokens; no client secrets stored.
- Legacy MSAL cache (if present) must be audited and removed on migration.

## 3. Token storage
- OS-protected per-profile token cache for Power Platform (MSAL cache file) — verify DPAPI/Keychain on Windows.
- Azure profiles use isolated Azure CLI profile directories (`AZURE_CONFIG_DIR`); ensure directory permissions are restricted.
- No tokens in SQLite databases (conversation store or Data_Memory).

## 4. Permission checks
- Azure resource inventory uses ARG with profile's existing RBAC; no privilege escalation.
- Power Platform environment discovery uses delegated permissions; 401/403 produces safe diagnostic messages.
- MCP tools validate required inputs (profile_id, environment_id).

## 5. Potential bypass risks
- Environment-variable inheritance for default Azure profile: if `AZURE_CONFIG_DIR` is unset, default CLI profile may be used unintentionally. Mitigation: always set isolated config dir.
- Auth job exception messages may leak internal details; ensure user-facing errors are sanitized.
- Path traversal in workspace metadata tools — verify canonicalization.
- Command runner must never use `shell=True`; use argument arrays.

## 6. Exploitability
- Low for read-only inventory tools. Higher risk if controlled runner is enabled without sandbox/approval/audit. Keep disabled until security-reviewed.

## 7. Mitigations recommended
- Restrict profile directory permissions on creation.
- Sanitize all exception messages returned to MCP clients.
- Add path canonicalization + allowlist checks in workspace tools.
- Implement audit logging hook in every MCP tool invocation.
- Add rate limiting / concurrency caps to prevent DoS.
- Keep arbitrary execution disabled.

## 8. Validation recommendations
- Unit tests for profile isolation, token redaction, path canonicalization, test-mode gating.
- Security review before enabling any write/execute capability.
- Periodic dependency scanning for azure SDK, msal, httpx.

## Conclusion
Read-only discovery surface is appropriately constrained. The primary risk is future enablement of the controlled runner without the required security boundary (see RUNNER_SECURITY_DESIGN.md). No code changes made in this audit.