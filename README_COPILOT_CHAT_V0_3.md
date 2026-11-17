# SKYFALL Copilot Chat v0.3

This patch connects the existing SKYFALL PySide6 desktop Chat page to the already-tested Copilot SDK session.

## What this patch adds

- A persistent Copilot SDK client/session owned by a background `QThread` and asyncio event loop.
- Streaming assistant text forwarded to the Qt UI through signals.
- The company-managed `auto` model route.
- The existing interactive Copilot CLI sign-in (`mode="copilot-cli"`).
- A SKYFALL system-message append that describes the current chat-only milestone.
- A permission callback that rejects tool permission requests in this milestone.
- A dedicated empty Copilot working directory under `%LOCALAPPDATA%\SKYFALL\copilot_chat_workspace`, not the project or operational workspaces.
- No SKYFALL custom tools, MCP servers, Azure connectors, Power Platform connectors, filesystem tools or command execution are intentionally registered.
- Graceful runtime shutdown when the desktop window closes.

## Files to copy

Extract the archive into the existing project root:

`C:\Users\pkara\Documents\Skyfall`

The archive contains only:

- `app/desktop/main_window.py` (replace the current file; make a backup first)
- `integrations/copilot/copilot_service.py` (new service)
- `integrations/__init__.py` and `integrations/copilot/__init__.py` (package markers)

It does not replace `main.py`, `requirements.txt`, `.venv`, configuration or user data.

## Run

From PowerShell:

```powershell
cd C:\Users\pkara\Documents\Skyfall
.\.venv\Scripts\Activate.ps1
python -m py_compile .\integrations\copilot\copilot_service.py .\app\desktop\main_window.py
python .\main.py
```

## Test in the app

1. Wait for the Overview's AI Runtime card to show `Connected`.
2. Open Chat.
3. Send: `Introduce yourself as SKYFALL and explain what you can do in this chat-only milestone.`
4. Confirm that text streams into the assistant message bubble.
5. Open the floating assistant, send a short message, and confirm it routes into the same main Chat conversation.
6. Close the application and confirm it exits normally.

## Important boundary

This milestone is conversational only. It is not an MCP or operational execution release. No Azure, Power Platform or local script tools are exposed by SKYFALL. The session's tool permission callback rejects tool permission requests. The UI must not claim that it has performed cloud or local operations.

## Version / compatibility

This patch is written against the SDK API shape validated by the user's successful connectivity test using `github-copilot-sdk==1.0.34`, including `CopilotClient(mode="copilot-cli")`, `create_session(model="auto", available_tools=[])`, and `send_and_wait(prompt)`. Do not update the SDK package as part of applying this patch.
