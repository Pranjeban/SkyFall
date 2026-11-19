# SKYFALL v1.1 — Universal Cloud Intelligence

**Superseded delivery label.** Per the user's latest instruction, implement this feature scope as v1.0.1. The active tracker is `releases/v1.0.1/README_SKYFALL_V1_0_1.md`; this earlier document remains as the original v1.1 scope record.

## Product goal

Use the supplied `Images/Design.md` as the product scope for one natural-language workspace across Azure and Microsoft Power Platform. SKYFALL should discover accessible cloud data, answer questions from live sources, compare environments, prepare useful reports, and eventually perform explicitly approved operations through a controlled boundary.

## Delivery sequence

| Phase | Scope | Current state |
| --- | --- | --- |
| 0 | Re-establish the requested desktop baseline and audit existing capabilities | UI source restored to the commit immediately before the Nov 18 Command Center redesign; capability audit complete |
| 1 | Unified identity, authentication health, tenant and subscription discovery | Profile, tenant and subscription discovery is already visible in the Azure page; architecture gap: brief names MSAL while current no-client-ID path uses Azure CLI |
| 2 | Broad, safe Azure resource inventory | Function App metadata inventory exists; general resource coverage is not implemented; next feature area after the identity architecture is settled |
| 3 | Power Platform environments, flows, apps, solutions, connections and Dataverse metadata | Environment and solution cloud-flow metadata discovery exist; remaining inventories are not implemented |
| 4 | Conversational live-data planning, cross-platform comparisons and follow-up context | Copilot/MCP and a v1.0 orchestration preview exist; unified live-data planning is not implemented |
| 5 | Reporting, health, cost, monitoring and anomaly detection | Local XLSX reporting exists for current inventories; other areas are not implemented |
| 6 | Controlled cloud operations, approved script execution, audit and governance | Cloud writes and general script execution remain disabled pending design of the approval and execution boundary |

## First implementation gate

Keep identity and discovery as the dependable, inspectable foundation before broadening resource types. Initial audit confirms the Azure page already displays registered profiles, tenant IDs, and accessible subscriptions, while the Azure manager exposes per-profile errors and partial-success results. Before changing sign-in, resolve the MSAL/Azure CLI architecture mismatch without violating the no-manual-client-ID preference. Then start the next feature slice: general Azure Resource Graph inventory using an explicit allowlist of non-secret metadata fields, with profile/subscription scope and local report output. Keep it read-only and never persist tokens in operation history.

Before changing sign-in, resolve the architecture mismatch between the brief's MSAL requirement and the working isolated Azure CLI flow. Preserve the user's preference not to enter a client ID. Do not add a client-ID prompt or change the active sign-in route until a supported, user-compatible approach is established.

## Existing foundation

- PySide6 desktop app, Copilot SDK integration, MCP server, capability registry, local SQLite conversation history, and approved workspace metadata index.
- Multiple isolated Azure CLI profiles with account, tenant, and subscription discovery.
- Read-only Azure Resource Graph inventory for Function Apps and local XLSX reporting.
- Power Platform account profiles, environment discovery, Dataverse solution cloud-flow metadata inventory, and local XLSX reporting.
- A v1.0 orchestration preview with visible stages and explicit approval for the built-in read-only flow inventory route.

## Safety and release rules

- Keep cloud discovery read-only while completing the identity and inventory foundations.
- Show which identity, tenant, subscription, and environment a request uses; never expose access tokens, secrets, or credential-cache contents.
- Preserve explicit approval for every operation that can change cloud state or execute user scripts.
- Do not present a planned or preview capability as complete. Keep the application version at 0.9.2 until the acceptance criteria in `Images/Design.md` are met and verified.
- Record capability and architecture decisions here as the milestone advances.
