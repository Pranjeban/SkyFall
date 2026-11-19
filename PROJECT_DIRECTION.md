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
- The active Power Platform environment and flow inventory path reuses isolated Azure CLI sign-in and Microsoft REST APIs; active app paths no longer require PAC CLI. A separate direct MSAL implementation remains in the account module but is not the current desktop sign-in path.
- Keep the user informed that Power Platform environment listing API is preview and documented Dataverse flow inventory excludes My Flows.

## v1.1 direction (2026-11-18)

The user has started the v1.1 milestone from `Images/Design.md`: build SKYFALL into a unified Azure and Microsoft Power Platform cloud intelligence workspace. Treat the document as a phased product scope, not as a requirement to implement every cloud operation at once. Keep operations read-only until an explicit approval and controlled execution boundary is designed and delivered.

- Restore the desktop interface to the version immediately before the 2026-11-18 Kiro-inspired Command Center redesign. Preserve the near-black workstation visual system and the existing cloud/account behavior from that baseline.
- Build in verifiable slices: identity and tenant/subscription foundation; Azure resource inventory; Power Platform inventory; natural-language orchestration; cross-platform comparisons; reporting/monitoring; then controlled operations, audit, and governance.
- The current code already discovers Azure CLI profiles, tenants/subscriptions, Power Platform environments, Function Apps, and solution cloud-flow metadata, and can create local Excel reports. It does not yet provide broad Azure resource inventory, Power Apps/solutions/connections inventory, cross-platform comparison, live-data conversational orchestration, monitoring, or approved cloud writes.
- Architecture review is required before replacing authentication. The brief names MSAL, while the active no-client-ID Azure and Power Platform sign-in path uses isolated Azure CLI profiles. Preserve the user's no-manual-client-ID preference and validate a supported migration path before changing login.
- Keep the app at 0.9.2 until v1.1 capabilities have been implemented and their acceptance criteria verified; do not advertise preview work as a release.

See `releases/v1.1/README_SKYFALL_V1_1.md` for milestone sequencing and current status.

## v1.0.1 implementation (2026-11-18)

The user has now explicitly asked to implement the complete `Images/V.1..0.1.md` scope under **v1.0.1**. Use `releases/v1.0.1/README_SKYFALL_V1_0_1.md` as the active delivery tracker; this overrides the earlier v1.1 delivery label while preserving the feature brief. The app's displayed version remains 0.9.2 until the milestone is complete.

Initial source implementation adds read-only general Azure Resource Graph inventory and Power Apps metadata inventory, both exposed through MCP and the capability catalogue with local XLSX reporting. These slices are implemented in source but have not been verified or visually exercised. Continue through the full brief in bounded slices; keep cloud writes and arbitrary script execution disabled until an approval and controlled-execution boundary is complete.

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

The v1.0 preview added a task-first Execution Center, ten labeled stages, safe account/tenant/environment display, and explicit confirmation for the built-in read-only Dataverse inventory route. This route does not execute workspace source. General script execution remains gated on a real security boundary. The desktop files have now been restored to the snapshot immediately before the Nov 18 Command Center redesign, per the user's direction; no cloud/account behavior was reverted.
