# SKYFALL v0.8.1 — Power Platform profile schema fix

This is a one-file overlay for SKYFALL v0.8.0.

## Root cause

The MCP wrapper exposed `start_powerplatform_login(profile_name: str = "", ...)`.
Because `profile_name` had a default, the generated MCP JSON schema marked it optional (`required: []`).
The SKYFALL v0.8 test correctly expects it to be required so Copilot collects a name before invoking the tool.

## Fix

The wrapper now declares `profile_name: str` without a default. Other arguments remain optional. The underlying account handler and confirmation guard are unchanged.

## Apply

Close SKYFALL. Extract this ZIP into the project root:

`C:\Users\pkara\Documents\Skyfall\`

It replaces only `skyfall_mcp/server.py`. It does not touch the virtual environment, Copilot sessions, local databases, Azure profiles, PAC profiles, workspace data, or existing scripts.

Then run:

```powershell
.\.venv\Scripts\Activate.ps1
python -m py_compile .\skyfall_mcp\server.py
python .\scripts\test_mcp_server.py
```

The schema assertion should now see `profile_name` in the required list. The smoke test runs in isolated test mode and must not authenticate or call cloud services.
