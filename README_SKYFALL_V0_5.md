# SKYFALL v0.5 — MCP Intelligence Framework

## What this release adds

- A local, stdio-based SKYFALL Core MCP server.
- A validated JSON capability catalogue.
- Three explicitly allow-listed, read-only tools:
  - `get_skyfall_status`
  - `list_skyfall_capabilities`
  - `describe_skyfall_capability`
- Copilot session configuration for the local MCP server.
- A dedicated Capabilities page in the desktop application.
- A stdio smoke test that discovers and invokes all three tools.

## Security boundary

This release does **not** enable Azure, Power Platform, Dataverse, Dynamics 365,
workspace indexing, arbitrary file access, PowerShell, Python script execution,
or report generation. The MCP server reads only SKYFALL's local capability
catalogue and returns application metadata. It has no external cloud credentials.

The Copilot session exposes only the three named core MCP tools. The local
server process is launched with the active SKYFALL virtual-environment Python
interpreter. The permission handler fails closed for any other tool request.

## Apply the patch

1. Close SKYFALL completely.
2. Back up these existing files before overwriting:
   - `main.py`
   - `app/desktop/main_window.py`
   - `integrations/copilot/copilot_service.py`
3. Extract this ZIP into the existing project root:
   `C:\Users\pkara\Documents\Skyfall`
4. In PowerShell, run:

```powershell
cd C:\Users\pkara\Documents\Skyfall
Unblock-File -LiteralPath .\setup_mcp_framework.ps1
.\setup_mcp_framework.ps1
```

The setup script preserves the old top-level `mcp` scaffold by renaming it to
`mcp_workspace_legacy`. This is necessary because a project folder named `mcp`
shadows the official third-party MCP SDK package also named `mcp`. Nothing is
deleted. If a backup folder already exists, setup stops rather than overwrite it.

The setup script appends `mcp>=2.0,<3.0` to the existing `requirements.txt` only
when an MCP SDK requirement is not already present. It installs into `.venv`
using pip's Windows trust-store support and verifies imports and dependencies.

## Validate the MCP server

```powershell
cd C:\Users\pkara\Documents\Skyfall
.\.venv\Scripts\Activate.ps1
python -m py_compile .\main.py .\app\desktop\main_window.py .\integrations\copilot\copilot_service.py .\skyfall_mcp\server.py .\skyfall_mcp\registry.py .\skyfall_mcp\tools\core.py .\scripts\test_mcp_server.py
python -m unittest discover -s .\tests\unit -v
python .\scripts\test_mcp_server.py
```

The stdio smoke test starts the server as a child process, lists tools, and
calls all three read-only tools. It does not make cloud calls or run scripts.

## Launch SKYFALL

```powershell
python .\main.py
```

When Copilot connects, the UI reports that the three SKYFALL Core tools are
available. In Chat, try:

- `Use SKYFALL Core to check your current application status.`
- `List the capabilities currently registered in SKYFALL.`
- `Describe core.get_status.`

A successful model answer should be grounded in tool results. The Capabilities
page also displays the local registry.

## Notes

- Do not run the setup script as Administrator unless your organization requires it.
- Do not weaken PowerShell execution policy or disable TLS certificate verification.
- If Windows marks the downloaded setup script as coming from the internet,
  `Unblock-File` removes that marker from this one script; it does not change
  execution policy.
- If installation fails because of corporate network policy, request the
  approved package index or certificate configuration from IT.
- This patch intentionally does not update the Copilot SDK version or runtime.
