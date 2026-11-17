# SKYFALL v0.9.1 — Power Platform Discovery & UI Refinement

## Release summary

SKYFALL v0.9.1 fixes Power Platform environment discovery for PAC CLI output differences and refreshes the Flow Inventory experience before the v1.0 orchestration milestone.

## 1. Power Platform environment discovery fix

The earlier implementation assumed `pac admin list --json` always returned parseable JSON. Microsoft documents both JSON output and the standard human-readable table form for `pac admin list`.

v0.9.1 now:

1. Tries `pac admin list --json` first.
2. Handles UTF-8 BOMs, ANSI terminal colour sequences and short CLI preambles around JSON output.
3. Normalizes recognized JSON array/envelope formats.
4. If JSON is unavailable or unparseable, retries with `pac admin list`.
5. Parses the documented aligned table output while preserving environment names containing spaces.
6. Returns a friendly, actionable permission/format message if both output modes fail; raw PAC output is not copied into chat.

Environment discovery remains read-only and uses the currently active PAC CLI profile. Tenant-wide visibility may require Power Platform administrative permissions.

## 2. Flow Inventory UI refinement

- Reworked the page into a scrollable, metric-led layout.
- Added summary cards for selected environment, visible flow count, enabled flows and report status.
- Added a clearer read-only status banner.
- Replaced the large blank table on first launch with a useful empty state.
- The flow preview table appears when results are available and is capped to a readable height.
- Added a contextual retry-environment-discovery action only when environment discovery needs attention.
- Improved loading, empty-result and failure messages.

## 3. Capabilities presentation

- Explicit styled backgrounds for capability cards.
- Increased minimum card height and description space.
- Preserved human-readable capability names and risk/category labels.

## 4. Naming and reporting

The v0.9 naming standard is retained:

`Platform-Resource-Scope-YYYY-MM-DD.xlsx`

Examples:
- `Azure-Function-Apps-All-Subscriptions-2026-11-17.xlsx`
- `Azure-Function-Apps-IT-CRM-Dev-2026-11-17.xlsx`
- `Power-Automate-Flows-IT-CRM-QA-2026-11-17.xlsx`

Repeated reports on the same date use a short sequence (`-02`, `-03`) rather than an opaque timestamp.

## 5. Safety boundaries

- Environment discovery is read-only.
- Flow inventory remains read-only and limited to the active PAC CLI profile's visibility in the selected environment.
- Flow definitions, action payloads, connection details and secrets are not exported.
- No Azure or Power Platform resource modifications are enabled by this release.
- No script execution is enabled by this release.

## 6. Validation performed

- Python `compileall`: passed.
- Unit tests: 74 passed.
- PAC table fallback parsing, JSON BOM/ANSI handling, friendly error handling and environment name preservation are covered by unit tests.
- Windows Qt rendering, actual PAC CLI environment discovery and MCP stdio subprocess smoke test still require verification on the user's Windows PC.
