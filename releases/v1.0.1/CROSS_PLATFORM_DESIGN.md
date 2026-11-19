# Cross-Platform Intelligence Design — SKYFALL v1.0.1

**Status:** Draft design (no code changes)
**Scope:** Phase 7 — Cross-platform intelligence

## 1. Purpose

Define how SKYFALL correlates and compares state across Azure and Microsoft Power Platform inventories, detects configuration drift between Dev / QA / Pre-Prod / Prod, and presents a consolidated inventory. Design-only; no implementation changes.

## 2. Source inventories (dependencies)

- Azure: `AzureFunctionAppInventory`, `AzureResourceInventory`, Azure profiles/subscriptions.
- Power Platform: flow inventory, app inventory, solution inventory, accounts/environments.

All inventories are read-only and never read secrets, connection details, app settings, or flow definitions.

## 3. Data models

### 3.1 Env ↔ Subscription relationship

```
EnvSubscriptionLink {
  link_id: UUID
  environment_id: UUID
  environment_name: str
  tenant_id: str
  azure_profile_id: str
  azure_subscription_id: str
  azure_subscription_name: str
  confidence: "exact" | "inferred" | "manual" | "none"
  evidence: list[str]
  created_at: datetime
  updated_at: datetime
}
```

### 3.2 Flow ↔ Connection relationship

```
FlowConnectionLink {
  flow_id: str
  flow_name: str
  environment_id: UUID
  solution_id: str | null
  connection_type: str
  connection_reference_count: int
  azure_dependency: AzureDependencyRef | null
}
AzureDependencyRef {
  subscription_id: str
  resource_type: str
  resource_id: str
  relation: "hosts" | "stores" | "triggers" | "unknown"
}
```

Connection identifiers and secrets are never stored. Only counts and abstract types.

### 3.3 App ↔ Solution relationship

```
AppSolutionLink {
  app_id: str
  app_name: str
  environment_id: UUID
  solution_id: str | null
  solution_name: str | null
  solution_version: str | null
  managed: bool | null
  containment: "inside_solution" | "unmanaged" | "unknown"
}
```

## 4. Configuration drift detection

1. Snapshot: persist normalized, redacted inventory snapshot per environment per run (local JSON, no secrets).
2. Normalize: canonicalize records.
3. Key: stable identity per record type.
4. Diff: set-based diff (added/removed/changed) plus field-level diffs.
5. Classify: added, removed, modified, renamed, state_changed.
6. Severity: low/medium/high based on resource type and environment tier.
7. Report: drift report (XLSX + JSON) with evidence.

Snapshot storage: `reports/cross_platform/snapshots/`, JSON with schema version, SHA-256 integrity, 30-day retention default.

## 5. Dev/QA/Pre-Prod/Prod comparison

Environments tagged with tier (dev, qa, preprod, prod, unknown) via name patterns + user assignment. Baseline = Prod. Pairwise matrix. Allowed-differences allowlist. Promotion readiness score 0–100. No automatic promotion.

## 6. Consolidated inventory aggregation

`ConsolidatedInventory` combining Azure + Power Platform inventories, join by keys, dedup by profile provenance. Output: XLSX workbook, JSON export, optional markdown summary. Mark `partial` if any source inventory failed; never fabricate records.

## 7. Dependencies

Cross-platform intelligence is a consumer of existing inventories. Required contracts: inventory functions return documented dict shapes with `success`, `status`, `errors`, `cloud_resources_modified`, `secrets_returned`. Records include stable IDs and provenance. No secrets.

## 8. Non-goals (v1.0.1)

No write operations, no reading flow definitions/connection details/app settings/secrets, no automatic promotion, no MSAL migration.

## 9. Risks

Heuristic linking false positives; ARG indexing lag; permission differences across tiers; solution membership requires metadata queries not yet implemented (treat as unknown).

## 10. References

- skyfall_cloud/azure_resources.py
- skyfall_cloud/powerplatform_resources.py
- skyfall_cloud/powerplatform_accounts.py
- skyfall_cloud/azure_profiles.py
- releases/v1.0.1/RUNNER_SECURITY_DESIGN.md
- releases/v1.0.1/ADR_AUTH_ARCHITECTURE.md
- releases/v1.0.1/README_SKYFALL_V1_0_1.md
