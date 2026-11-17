# SKYFALL MCP diagnostic hotfix

The v0.7.1 smoke test discovers the 17 tools and passes core/workspace checks, then fails inside the Microsoft-account-tool phase with a generic `ExceptionGroup`. This update does not change cloud/account functionality. It improves the smoke test so the next run identifies the exact tool call and prints nested exception details. It also checks that `start_powerplatform_login.profile_name` is optional in the published MCP schema.

## Apply

Close SKYFALL and replace only:

`C:\Users\pkara\Documents\Skyfall\scripts\test_mcp_server.py`

with the included file. No other application or data files change.

## Run

```powershell
cd C:\Users\pkara\Documents\Skyfall
.\.venv\Scripts\Activate.ps1
python .\scripts\test_mcp_server.py
```

The diagnostic runs with `SKYFALL_TEST_MODE=1` in its child process, uses an isolated temporary database, and does not sign in or access cloud resources. Share the complete output if it still fails.
