# SKYFALL v0.9.0 — Power Platform Resource Intelligence

## Release summary

SKYFALL v0.9.0 fixes the Capabilities layout, standardizes user-facing names and report filenames, and adds read-only Power Automate cloud-flow inventory with local Excel reporting.

## What's included

### Capabilities page correction
- Scrollable two-column capability-card grid.
- Explicit card, title, description, category and risk styling.
- Fixed minimum card dimensions so the page no longer compresses the capabilities into empty horizontal bars.
- Plain-language capability names are shown to users; technical MCP IDs remain internal/tooltip metadata.

### Naming convention
- User-facing capabilities use clear action-oriented language such as **Discover Azure Function Apps**, **Check Azure Connection**, and **Generate Power Automate flow inventory**.
- Report filenames follow `Platform-Resource-Scope-YYYY-MM-DD.xlsx`.
- Dots and underscores in scope names are normalized to hyphens (for example `IT.CRM.Dev` becomes `IT-CRM-Dev`).
- If a report with the same name already exists, a short sequence (`-02`, `-03`) prevents overwriting; opaque timestamps are not used.

Examples:
- `Azure-Function-Apps-All-Subscriptions-2026-11-17.xlsx`
- `Azure-Function-Apps-IT-CRM-Dev-2026-11-17.xlsx`
- `Power-Automate-Flows-IT-CRM-QA-2026-11-17.xlsx`

### Azure Function App inventory
- Existing read-only Azure Resource Graph inventory is preserved.
- Azure reports now use the shared readable filename helper.
- Reports continue to exclude app settings, connection strings, publishing profiles, host keys, function keys and secrets.

### Power Automate cloud-flow inventory
- Adds `PowerPlatformFlowInventory` for an explicitly selected environment.
- Adds MCP tool `inventory_power_automate_flows` with a required `environment_id`.
- Uses the currently active PAC CLI profile and the `pac power-automate list-cloud-flows --environment <id> --json` command.
- Generates a six-sheet report: `Overview`, `Cloud Flows`, `Status Summary`, `Flow Types`, `Owners`, and `Discovery Notes`.
- Returns a concise preview and a descriptive local report filename.
- Exports allow-listed metadata only; definitions, action payloads, connection details, credentials and secrets are excluded.
- Formula-like metadata is escaped before being written to Excel.

### MCP and Copilot
- Capability registry and Copilot allow-list now contain 19 tools.
- Friendly tool titles are used in the MCP interface.
- MCP smoke tests verify the required environment ID and confirm that cloud inventory is blocked in isolated test mode.

## Permissions and limitations

- Flow inventory is read-only against Power Platform; report generation writes a local XLSX file.
- Inventory coverage is limited to flows visible to the current PAC CLI profile in the selected environment.
- Microsoft currently documents the PAC CLI `list-cloud-flows` command as Preview.
- SKYFALL does not silently switch PAC CLI profiles.
- Resource modification, flow activation, solution deployment and script execution are not enabled.

## Validation performed for this package

- Python compileall: passed.
- Unit tests: 70 passed.
- Actual Windows Qt rendering and MCP STDIO subprocess test: must be verified on the user's PC after installation.
