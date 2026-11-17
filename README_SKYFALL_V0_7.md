# SKYFALL v0.7 — Microsoft Account Intelligence

## Summary

Version 0.7 adds read-only Azure CLI and Power Platform CLI account/environment discovery. It preserves the v0.6 desktop shell, Copilot-powered chat, local conversation history, metadata-only workspace intelligence and existing seven MCP tools.

## Azure

`AzureProfileStore` maintains non-secret profile metadata under `%LOCALAPPDATA%\SKYFALL\azure_profiles\profiles.json`. The built-in `azure-cli-default` profile reads the user's normal Azure CLI configuration. Additional named profiles each get their own `AZURE_CONFIG_DIR` folder under the same SKYFALL directory. Sign-in is user-driven using `az login --use-device-code`, optionally scoped to a specified tenant. SKYFALL never copies token data into its own profile registry.

Tools can query one profile or `all` registered profiles. Subscription discovery uses `az account list --all`; a refresh appends `--refresh`. Tenant discovery deduplicates tenant IDs represented in profile subscription/account metadata. The Azure CLI experimental tenant extension is intentionally not installed or invoked.

## Power Platform

`PowerPlatformDiscovery` lists PAC CLI auth profiles and identifies the active one. It uses `pac admin list --json` for environment discovery. The command is scoped to the currently active PAC profile and may require tenant administrative privileges. SKYFALL does not call `pac auth select`, so it will not silently change global PAC CLI state.

The PAC `auth list` output is a human-readable table; its parser is best-effort and has unit coverage for the documented table layout. If a future PAC CLI build changes the table, profile parsing may need adjustment.

## MCP tools

The MCP server now exposes 14 tools total: 3 core, 4 workspace metadata, 4 Azure discovery and 3 Power Platform discovery tools. Copilot's explicit allow-list includes only these names. All new tools are marked `read_only`, do not require write approvals and have no resource-modification side effects.

## UI

- Azure page: all connected profiles selector, isolated profile creation instructions, authentication status, tenant IDs and subscription inventory.
- Power Platform page: PAC profile inventory, active-profile status and environment inventory.
- Both pages run CLI discovery in a background QThread so the desktop does not block.

## Out of scope

No Azure resource inventory beyond subscriptions, no Function App inventory yet, no Power Platform flow inventory, no resource changes, no PAC profile switching from the UI, no script execution, no source-code retrieval and no report generation.
