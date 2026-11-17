# SKYFALL project direction

This note captures the user's stated product direction so future SKYFALL work can pick up consistently.

## Product goal

- Treat the current cleanup and workflow improvements as part of the v0.9.2 milestone if needed.
- Do not move SKYFALL to v1 until the current rough edges and requested changes are addressed.
- The app should feel organized and dependable as a local engineering workspace, especially during a long local session.
- When asking for implementation work, the user prefers direct code changes in the project.

## Current priorities

- Reduce clutter in the local chat/session area and organize the side workflows so they are easier to scan.
- Use a more professional color palette. The previous chat canvas/background was strongly disliked and needs to remain comfortable and readable.
- Let users delete a conversation from the app.
- Fix Power Platform profile dropdown behavior so profile use does not require going through “Manage profiles” each time.
- Power Platform profile, environment discovery, and flow inventory now use per-account MSAL OAuth plus Microsoft REST APIs; active app paths no longer require PAC CLI.
- Keep the user informed that Power Platform environment listing API is preview and documented Dataverse flow inventory excludes My Flows.

## Implementation context from the latest update

- SKYFALL is a Windows/PySide6 desktop app.
- Chat history is indexed in a local SQLite database (`memory/conversation_store.py`). Copilot SDK session transcripts are stored separately.
- Power Platform accounts are stored in a SKYFALL-local registry; each profile keeps an OS-protected MSAL token cache and its own selected environment.
- Environment discovery uses the Power Platform REST API. Flow metadata inventory uses the Dataverse Web API for solution cloud flows.
- UI entry points are in `app/desktop/main_window.py`; the shared stylesheet is in `app/desktop/theme.py`.
- The latest changes added a local conversation delete control, sidebar group labels, slate chat styling, and integer normalization for Power Platform profile IDs. These have only had syntax and diff checks; the app has not been visually exercised yet.
- v0.9.2 adds the non-PAC OAuth route, persistent account/environment selection, profile management UI, diagnostics, and regression tests. The app still needs visual QA on a machine with its declared dependencies installed.
- Screenshots provided from the `Images` folder show the sidebar's `LOCAL SESSION` card clipped at the bottom beneath “Open floating assistant.” The navigation is now placed in its own scroll area, with the assistant action and compact local status card anchored below it so those controls remain visible as the window height changes.

## Follow-up

The user linked a ChatGPT conversation for fuller context, but its contents were not accessible in the current session. Add details from that conversation here if the user supplies an export or transcript.

## v1.0 orchestration direction (2026-11-17)

User introduced Intelligent Engineering Orchestration as the next major milestone. Core flow: approved-workspace search; exact script identification; parameter/dependency inspection; explicit environment resolution; identity/auth validation; concrete plan; user approval; controlled execution; result validation; report delivery. They want a persistent progress bar with credential identity context, and a major professional UI update inspired by Dribbble/Behance.

v1.0 preview UI work is in progress: task-first Execution Center, ten labeled stages, monotonic plan progress + indeterminate run progress, safe account/tenant/environment display, and explicit confirmation for the built-in read-only Dataverse inventory route. This route does not execute workspace source. General script execution remains gated on a real security boundary; do not mark v1.0 released until that runner and all ten steps are implemented and tested. A light stone/slate/blue-teal theme is being applied based on automation dashboard layouts and Fluent progress guidance.
