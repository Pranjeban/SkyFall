# SKYFALL v0.4 — Local Conversation Memory

## What this update adds

- Local SQLite conversation index and visible message history.
- Multiple conversations with a New Conversation button and history list.
- Per-conversation stable Copilot session IDs.
- Copilot SDK session resume after the desktop app restarts.
- SKYFALL assistant identity and clearer chat-only safety boundaries.
- A settings entry showing the local conversation database location.
- No new Python dependencies.

## Files in this patch

- `app/desktop/main_window.py` — updated Chat page, history panel and session switching.
- `app/desktop/theme.py` — conversation-list styles.
- `integrations/copilot/copilot_service.py` — creates/resumes one Copilot SDK session per local conversation.
- `memory/__init__.py` and `memory/conversation_store.py` — SQLite storage.
- `tests/unit/test_conversation_store.py` — local storage tests.

## Apply

1. Close SKYFALL completely.
2. Back up these existing files:
   - `app/desktop/main_window.py`
   - `app/desktop/theme.py`
   - `integrations/copilot/copilot_service.py`
3. Extract the ZIP into the existing project root:
   `C:\Users\pkara\Documents\Skyfall`
4. Allow those three application files to be overwritten. The patch does not include `main.py`, `.venv`, `requirements.txt`, or your existing Copilot test script.
5. Run the validation commands below before starting the app.

## Validation

```powershell
cd C:\Users\pkara\Documents\Skyfall
.\.venv\Scripts\Activate.ps1
python -m py_compile .\app\desktop\main_window.py .\app\desktop\theme.py .\integrations\copilot\copilot_service.py .\memory\conversation_store.py
python -m unittest discover -s .\tests\unit -v
```

Then launch:

```powershell
python .\main.py
```

## Verify these behaviours

1. Existing current conversation appears in the history panel.
2. Send a message and wait for a completed response.
3. Create a new conversation; it should start empty.
4. Send a different message in the new conversation.
5. Switch back to the first conversation; its transcript should appear.
6. Close SKYFALL and reopen it; the last active conversation should resume.
7. Ask SKYFALL what you discussed earlier in that same conversation; it should use the resumed Copilot session context.

## Data locations and privacy

- SKYFALL's local conversation database: `%LOCALAPPDATA%\SKYFALL\data\skyfall.db`
- Copilot SDK session state: the existing Copilot CLI home under the signed-in Windows user profile, in its `session-state` folder.

Conversation text is sent to the GitHub Copilot service under the signed-in company account and is also persisted locally as described above. The SQLite database is not application-encrypted in v0.4; it resides under the signed-in Windows user profile and relies on Windows account/file permissions. Do not store secrets in conversations. No passwords, access tokens, client secrets, or connection strings should be entered into chat.

This release is still chat-only. It does not inspect workspace folders, invoke MCP tools, access Azure or Power Platform, or execute local scripts.

## Recovery note

If an SDK session cannot be resumed (for example, its Copilot session-state files have been removed), the local SQLite transcript remains available, but the assistant may not have the original model context. Create a new conversation to continue. This patch does not automatically delete Copilot session-state files when a local conversation is removed.

## Migration from v0.3

The v0.3 test/chat session did not store a stable session ID in SKYFALL's database, so it cannot be automatically imported into the new conversation list. The first launch of v0.4 creates a new persistent conversation. Any old v0.3 Copilot session data is left untouched in the Copilot session-state directory.
