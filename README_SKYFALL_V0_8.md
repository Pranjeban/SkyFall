# SKYFALL v0.8.0 — Azure Resource Intelligence

This release adds a read-only Azure Function App inventory capability and a local XLSX report workflow. It preserves the v0.7.1 Copilot chat, conversation memory, workspace metadata indexing, Microsoft profile discovery and account management.

## What's included

- `inventory_azure_function_apps` MCP tool.
- Azure Resource Graph REST API integration (`2022-10-01`).
- Uses the selected SKYFALL Azure CLI profile(s); `profile_id="all"` queries all registered authenticated profiles.
- Discovers enabled subscriptions visible to each selected profile.
- Supports an optional subscription-ID allow-filter. Requested IDs must already be visible to the selected profile(s).
- Reads Function App resource metadata, runtime/stack hints, hosting-plan SKU/tier, selected site configuration, networking metadata, identity type and resource tags.
- Paginates Azure Resource Graph results and refuses to claim success when a result is known to be truncated without a continuation token.
- Generates a detailed local workbook under `reports/Azure`.
- Adds an Azure Resources desktop page with a background inventory action and a preview of the results.
- Fixes the Azure subscriptions grid's Account profile column for a single selected profile.

## Important safety boundaries

The Azure operation is read-only. It does not create, update, delete, restart or reconfigure Azure resources.

The inventory deliberately does **not** request or include:

- Function App application settings.
- Connection strings.
- Publishing profiles or publishing credentials.
- Host keys or function keys.
- Other secret-bearing configuration endpoints.

Tag values are exported after heuristic redaction for keys that look secret-bearing (for example, `password`, `secret`, `token`, `credential`, `connectionString`, `SAS` and private/access keys). This is not a guarantee that all sensitive tag values are detected; review organizational tagging practices before sharing the workbook. Formula-like text from external resource metadata is escaped before writing cells so Excel does not treat it as a formula.

Azure Resource Graph is an indexed resource inventory. Its data can lag a recent resource change. Resource Graph query permissions are required; an account can be authenticated but still lack the permissions needed to query some subscriptions. SKYFALL reports per-profile/hosting-plan errors and labels partial results rather than silently claiming complete coverage.

The only local write performed by this capability is an XLSX workbook under the project's `reports/Azure` directory. No source workspace files are modified.

## Workbook sheets

1. **Summary** — generated time, profile/subscription/app counts, region and state counts, safety/completeness notes.
2. **Function Apps** — app, subscription, tenant, resource group, region, state, OS/runtime, Functions runtime, hosting plan SKU/tier, HTTPS/network state, selected configuration, identity type and resource ID.
3. **Hosting Plans** — plan SKU/tier/size, kind, region, OS reservation and scale/worker metadata.
4. **Configuration** — runtime and selected non-secret runtime settings.
5. **Networking** — HTTPS, public network access, VNet subnet ID and identity type.
6. **Tags** — sanitized resource tags.
7. **Discovery Errors** — profiles/stages that could not be queried or enriched.

## Installation

1. Close SKYFALL.
2. Back up the files listed in `README_FIRST.md`.
3. Extract the release ZIP into the existing SKYFALL project root. Do not extract it into a new nested folder.
4. No new Python package is required; v0.7.1 already includes `httpx` and `openpyxl`.
5. Run the validation commands in `README_FIRST.md`.
6. Launch `python .\main.py`.

## Using SKYFALL

### Chat

Try:

> Skyfall, fetch all Function Apps across my accessible Azure subscriptions and generate a detailed Excel report.

For a named scope:

> Skyfall, inventory Function Apps in the QA subscription.

SKYFALL should discover subscriptions first. If more than one subscription matches QA, it must ask which one rather than guessing.

### Azure Resources page

Open **Azure Resources** and select **Generate Function App Excel inventory**. The page uses the profile currently selected on the Azure page. Choose **All connected Azure accounts** on the Azure page to query all registered profiles.

## Output

`reports/Azure/Azure_FunctionApp_Inventory_<UTC timestamp>.xlsx`

## Test mode

The MCP smoke test starts the server with `SKYFALL_TEST_MODE=1`. In this mode the Function App inventory tool returns `blocked_test_mode` before calling Azure CLI or making network requests. The test verifies registration and the safety guard without accessing real cloud resources.

## Release boundary

Enabled: Azure Function App inventory and local XLSX report generation.

Not enabled: arbitrary shell execution, PowerShell/Python script execution, resource modification, app-settings retrieval, deployment, restart, scaling changes, or remediation.
