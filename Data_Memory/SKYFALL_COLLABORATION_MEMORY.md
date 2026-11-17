# SKYFALL Collaboration Memory

This folder is the local project memory for ongoing SKYFALL work. Update it when the user establishes a durable preference, reports a new issue, changes milestone priorities, or when implementation status changes. Keep issue screenshots in `Images/` and reference them from this memory. Keep version-specific implementation notes in `../releases/vX.Y.Z/`.

> The requested canonical location was `C:\Users\pranj\OneDrive\Documents\Skyfall(1)\Data_Memory`. The current coding workspace can write only inside the nested `Skyfall` project, so this working memory is stored at `Skyfall/Data_Memory` until it can be moved by the user or a session with write access to the parent folder.

## Product direction and user preferences

- Product: SKYFALL, a local Windows/PySide6 engineering workspace with Copilot integration.
- User wants direct code changes in the project when asking for implementation.
- Keep the product at v0.9.2 until the existing UX and workflow rough edges are resolved; do not move to v1 prematurely.
- Keep a separate Markdown release/history file for every version under `releases/vX.Y.Z/`.
- Maintain this memory across sessions. It should capture decisions and reported issues; do not assume external ChatGPT conversation links were imported automatically.
- User supplied ChatGPT links for context:
  - `https://chatgpt.com/g/g-p-6afc544b35c08191ad19fdc5ce174f34-skyflow/c/6afb4234-1984-83ee-adc2-5d854c0faae4`
  - `https://chatgpt.com/share/6afc77a4-9ff8-83e8-ab36-763434bd96a8`
  Their contents have not been captured in this local workspace; request an export if specific missing details matter.

## Reported product issues and desired outcomes

1. PAC CLI causes problems. Prefer a supported direct Microsoft API/OAuth path that avoids depending on PAC CLI for SKYFALL's Power Platform features.
2. Power Platform account/profile/environment dropdown is unreliable; the user had to enter Manage each time. Make profile selection direct and persistent, and preserve per-account environment selection.
3. Local Session is cluttered and side workflows need a clearer hierarchy.
4. The box beneath “Open floating assistant” is clipped or difficult to see, with other components below it. Keep those controls visible and organize the sidebar at different window heights.
5. Chat background color is strongly disliked; use a professional, comfortable palette and improve message contrast/readability.
6. Add conversation deletion/management.
7. Add clearer errors/diagnostics and regression coverage.
8. User identified `C:\Users\pranj\OneDrive\Documents\Skyfall(1)\Images` as the place containing issue screenshots. Keep reference images with this memory folder for future comparisons.

## v0.9.2 work recorded (2026-11-17)

- Added `skyfall_cloud/powerplatform_accounts.py`: SKYFALL-local account store, MSAL delegated OAuth, OS-protected per-profile token cache, Power Platform environment discovery, Dataverse metadata inventory, safe pagination host checks.
- Migrated active desktop, worker, Copilot, and MCP Power Platform paths off PAC CLI.
- Added public client ID configuration and account management UI; selected environment stored per account.
- Updated professional slate chat theme and sidebar layout; Local Session and floating assistant controls are anchored below scrollable navigation.
- Added conversation deletion.
- Added API diagnostic codes and tests for accounts, environment pagination, permissions, and flow inventory.
- Added release notes in `../releases/v0.9.2/README_SKYFALL_V0_9_2.md`.
- Important implementation limitation: Power Platform Environment Management list API is preview. The documented Dataverse code path supports solution cloud flows; My Flows is not supported. This should be clearly communicated in UI/help/docs.
- Verification: Python syntax compilation and `git diff --check` passed. Unit tests could not run in the available Python because `httpx` (and other app dependencies) are absent; the checked-in `.venv` also points to a missing interpreter. Full desktop visual QA is pending on a configured Windows environment.

## Screenshot index

- `Images/unnamed.png` — provided issue screenshot. Previously reviewed as evidence of the sidebar Local Session area being clipped beneath the floating assistant action; retain it as a before-state reference.

## Update protocol

For future SKYFALL work:

- Append dated entries under a new “Session updates” heading, preserving older context.
- Update issue status (open / in progress / addressed / needs visual verification) instead of deleting user-reported problems.
- Copy new user-provided issue images into `Images/` and add one-line descriptions here.
- Keep secrets, access tokens, and personal credentials out of these files.

## Conversation list cleanup (2026-11-17)

The screenshot `Images/conversation-ghost-after-delete.png` shows empty rows labeled “New conversation” after deleting chat history. The user also referenced `C:\Users\pranj\OneDrive\Documents\Skyfall(1)\Images\issue.txt`; that file is empty (0 bytes), so the screenshot and the user's description provided the issue details.

Fix: `ConversationStore.list_conversations()` now returns only conversations with at least one stored message. Empty drafts still exist as the active working chat, but do not appear in the history list. This also hides previously accumulated blank rows. Added `test_empty_drafts_do_not_appear_in_conversation_history`, which confirms empty drafts stay hidden and a draft appears after its first user message. `python -m unittest tests.unit.test_conversation_store` passed (8 tests).
