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

## MCP stdio smoke-test startup failure (2026-11-17)

User ran `scripts/test_mcp_server.py` from `C:\Users\pkara\Documents\Skyfall\SkyFall`; MCP client negotiation failed with `mcp.shared.exceptions.MCPError: Connection closed` before tools were listed. This traceback identifies that the stdio child closed before initialization, but the original harness did not show its startup/import error.

The test script also still had v0.9.1 expectations: 19 tools, no `configure_powerplatform_app`, and PAC CLI confirmation behavior. Updated it to v0.9.2 (20 tools), verify the new app-ID setup and OAuth prerequisite, and run a child-interpreter import preflight that captures stdout/stderr and reports import errors before protocol negotiation. Failure output is now concise. Script syntax compilation and `git diff --check` pass. The end-to-end MCP test still needs to be rerun in the user's configured Python 3.11 environment; this workspace's available venv points to a Python installation unavailable here.

## MCP server import failure fixed (2026-11-17)

The child import preflight reported the exact failure: `ImportError: cannot import name 'start_azure_login' from 'skyfall_mcp.tools.accounts'` at `skyfall_mcp/server.py` line 16. The account tool module had been rewritten for Power Platform OAuth without restoring its Azure login entry point, while the MCP server still registered and imported that tool. Restored `start_azure_login` with isolated Azure profile creation/sign-in, existing-profile support, missing-input responses, and a `SKYFALL_TEST_MODE` guard. Added unit coverage for missing profile/tenant input and test-mode blocking. Python compilation, AST verification of all account imports, and `git diff --check` pass. Full MCP stdio execution remains to be verified in the user's Python 3.11 environment.

## Unit test expectation fixes (2026-11-17)

User ran all 77 tests and reported two assertion failures. Updated `test_core_mcp_tools.py` to expect 20 total enabled tools and 4 Power Platform discovery tools (the added `configure_powerplatform_app` capability). Updated the client ID error regex in `test_powerplatform_accounts.py` to escape literal parentheses in `Application (client) ID GUID`. Reran core MCP tests (4 passed) and Power Platform account tests (5 passed; `httpx` stubbed only to satisfy an import in this dependency-limited workspace; tests use a fake HTTP client). `git diff --check` passed.

## MCP test confirmed working (2026-11-17)

User confirmed: “good now it is working”. Mark the MCP stdio startup/import issue and stale unit assertions resolved. Keep the v0.9.2 test and Azure login restoration notes for history.

## v1.0 milestone accepted and started (2026-11-17)

The user named Intelligent Engineering Orchestration as the next major milestone, requesting ten stages from workspace discovery through report delivery, identity/progress visibility, and a major professional redesign with Dribbble/Behance inspiration. Created `releases/v1.0/README_SKYFALL_V1_0.md` as the acceptance/architecture record. Started a preview Execution Center with staged plan progress, safe identity context, and a reviewed native inventory route. This is not a completed v1.0 release: arbitrary workspace script execution remains disabled pending a controlled security boundary.

## v1.0 Execution Center preview implemented (2026-11-17)

- Added a task-first Execution Center with approved-workspace script metadata search, parameters/imports summary, explicit account/tenant and environment context (no secrets), ten visible run stages, monotonic planning progress, indeterminate network progress, and explicit confirmation before the built-in read-only Dataverse Flow Inventory report run.
- Added a professional light stone/slate/blue-teal palette across app surfaces and chat for better long-session contrast. Sidebar nav label is now Orchestration.
- Design references reviewed: Dribbble AI Workflow Builder, Behance Nexora automation dashboard, Microsoft Fluent progress bar/wait UX. See `releases/v1.0/README_SKYFALL_V1_0.md`.
- Important scope: this first wired route shows workspace script metadata but does not execute workspace source; it runs SKYFALL's native read-only inventory API. A general script runner is still gated on an actual security boundary. The app remains version 0.9.2 until all v1.0 execution/validation requirements are complete.
- Verification: `py_compile` and `git diff --check` passed. Visual QA not performed because PySide6 is unavailable in this workspace's active interpreter.


## Kiro-inspired visual redesign (2026-11-17)

User feedback: the light v1.0 redesign looked very bad (especially the white chat canvas and black sidebar navigation block). User shared a Kiro Crew screenshot and requested a detailed Kiro-inspired scheme, glass styling, and a more polished overall UI. Replaced the light direction with graphite/plum surfaces, muted lavender navigation, violet accents, layered translucent cards, consistent dark styling for chat/Markdown, dialogs, tables, profile selectors, and floating assistant. Explicitly themed `sidebarNavigationContent` to eliminate the black rectangle. Design reference: https://kiro.dev/ and user-provided screenshot. Status: code updated; launch-and-render visual check still needed on a PySide6-enabled Windows environment.

## Power Platform Azure-style sign-in (2026-11-17)

User asked for Power Platform to use the same sign-in pattern as Azure and then list environments available to the signed-in account. Aligned the flow to one profile creation dialog (profile name plus optional tenant), Microsoft browser sign-in, automatic environment discovery, a refresh action, and a saved per-profile environment selector. Kept direct OAuth and removed no app registration requirement: Microsoft Learn states Power Platform API use requires an app registration. The PAC CLI is not used. Version note appended to `releases/v0.9.2/README_SKYFALL_V0_9_2.md`. Code updated; Windows live-account verification remains pending.


## Power Platform no-client-ID sign-in correction (2026-11-17)

The user shared a screenshot showing Add profile still opening a client ID dialog and explicitly said they will not enter a client ID. Replaced that desktop path with Azure's own browser login in a new isolated Azure CLI profile. The profile is linked to Power Platform, then environment discovery obtains short-lived tokens from that isolated CLI cache and calls the Power Apps environments API. Dataverse flow inventory uses a resource token for the selected Dataverse URL. The profile form keeps name and optional tenant only; no client ID prompt. Power Platform API setup note has been revised. The environment list is shown after sign-in; only environments with a Dataverse URL populate the flow inventory selector. Added removal of linked isolated profile on confirmed account removal. Official basis: Microsoft Dataverse-skills repo documents Azure CLI fallback via `az account get-access-token --resource https://service.powerapps.com/` and the Power Apps environments endpoint. Status: source updated; live Microsoft sign-in still requires the user's configured Windows environment to verify.


## Kiro-style shell and chat refinement (2026-11-17)

User requests the whole SKYFALL desktop shell to follow the supplied Kiro Crew screenshot closely: rounded app silhouette and cards, graphite/plum palette, violet accent, two-rail session/chat layout, and smooth scrolling. Implemented a lavender outer surround, rounded dark appSurface, simplified searchable session rail with compact New/actions, selected conversation title, rounded composer, eased wheel scrolling and thin scrollbars. The app version remains v0.9.2. `python -m py_compile app/desktop/main_window.py app/desktop/theme.py` passed; PySide6 is unavailable here, so actual rendered visual QA remains outstanding.


## Design.md visual language applied (2026-11-17)

User provided `C:\Users\pranj\OneDrive\Documents\Skyfall(1)\Images\Design.md` and asked to implement it. The brief specifies a quiet premium workstation, near-black/violet charcoal, neutral layers separated by small luminance steps, rare accent color, softened contrast, smoked-glass treatment, restrained shadows, consistent 10/14/18/24px radii, and minimal scrollbars/motion. The latest `app/desktop/theme.py` block implements these values and overrides the earlier brighter Kiro palette. `main_window.py` also updates floating assistant hardcoded colors, status bar, and smooth wheel duration. Qt stylesheet does not support actual backdrop blur; the surface uses layered fills and subtle reflections as a practical approximation. App stays at v0.9.2. Syntax/diff checks passed; visual QA awaits a PySide6 Windows run.
