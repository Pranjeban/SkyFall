# SKYFALL v0.9.2 — Account, Session, and Workspace Refinement

## Release intent

This milestone addresses the issues that block moving SKYFALL toward v1: a stable Power Platform connection, saved Microsoft accounts, clearer session management, and a calmer professional visual system.

## Power Platform connection

- Active application flows no longer require PAC CLI.
- Desktop sign-in reuses Azure CLI's browser login in a named, isolated SKYFALL profile; users do not enter a Power Platform client ID and SKYFALL does not use PAC CLI.
- Power Platform accounts link to isolated Azure profiles. Azure CLI owns and protects the per-profile token cache; environment selection persists per Power Platform profile.
- Environment discovery uses the Power Apps environments API with a short-lived Azure CLI token for `https://service.powerapps.com/`, following Microsoft's Azure CLI fallback guidance: https://github.com/microsoft/Dataverse-skills/blob/main/.github/plugins/dataverse/skills/dv-connect/references/mcp-configuration.md
- Cloud-flow inventory uses the Dataverse Web API and only requests metadata. Microsoft's documented code path supports solution cloud flows and does not support My Flows: https://learn.microsoft.com/en-us/power-automate/manage-flows-with-code
- Flow inventory obtains a short-lived token for the selected Dataverse environment through the same isolated Azure CLI profile. The account must have access to that environment and permission to read its cloud-flow metadata.

## UI and session work

- Rebalanced the app to a professional slate palette and improved chat canvas/message contrast.
- Kept navigation independently scrollable and anchored the floating assistant and local session controls so the session card remains visible.
- Added local conversation deletion and tightened selection behavior after deletion.
- Reworked Power Platform settings around saved Microsoft accounts and persistent environment selection; choosing an account no longer routes through Manage each time.
- Kept this milestone at v0.9.2; v1 remains gated on resolving the current UX and workflow issues.

## Diagnostics and regression coverage

- API errors provide stable diagnostic codes and actionable permission, not-found, and throttling guidance.
- Pagination follows only HTTPS links on the expected Microsoft host.
- Regression tests cover profile persistence/removal, environment pagination, safe error output, flow inventory metadata, and capability registration.

## Verification limits

The changed Python modules were syntax-compiled and the patch was checked for whitespace errors. The full test suite and desktop visual QA could not be run in the current environment because the project dependencies are unavailable and the checked-in virtual environment points to a missing Python installation. Run the project test suite and inspect the UI on a configured Windows development machine before packaging.

## Conversation history cleanup

Empty draft conversations are omitted from the sidebar history until the user sends the first message. This prevents blank “New conversation” rows from accumulating after deletion while preserving the active draft.

## MCP stdio smoke-test updates

The smoke test now matches v0.9.2's tool set and account setup. It performs an isolated child-process import preflight and reports import errors before MCP handshake, then formats connection/task-group failures more clearly. Run the test in the configured Python environment to complete end-to-end verification.

## MCP Azure login import repair

Restored the Azure MCP account-login tool that the server imports: new named isolated Azure profile login and existing-profile sign-in run as an authentication job. Test mode blocks external login. Regression coverage added for missing inputs and the test-mode guard.

## Unit regression count/string fixes

Updated v0.9.2 capability counts (20 total tools, 4 Power Platform discovery tools) and corrected the regex so literal parentheses in the client ID validation message match correctly.

## Power Platform account flow update (2026-11-17)

Aligned Power Platform sign-in with Azure's profile-first workflow: Add profile opens one form for a profile name and optional tenant, then immediately opens Azure's Microsoft browser sign-in in a new isolated profile. Environment discovery runs automatically after sign-in, and a Refresh environments control is available. All accessible environments appear in the account page; Dataverse-enabled environments also appear in the flow inventory selector, with the selection saved per profile. Power Platform and Dataverse access tokens are requested through Azure CLI for the relevant resource and remain in the isolated Azure profile cache. This removes PAC CLI and the manual client ID/app registration prompt. Environment lookup uses Microsoft's Power Apps environments API; flow inventory uses read-only Dataverse metadata.

## Kiro-inspired rounded desktop shell (2026-11-17)

Reworked the desktop frame around a lavender surround and rounded graphite/plum app surface. The chat uses a focused two-rail layout with a searchable session list, compact New/action controls, rounded conversation rows, an understated message canvas and a framed composer. Added eased wheel scrolling and slim low-contrast scrollbars across scroll pages. Violet is reserved for selected/focused states and primary actions. This follows the user-provided Kiro Crew screenshot as a visual reference; SKYFALL implementation and branding remain its own.

Verification: Python syntax compilation passed. PySide6 is unavailable in the current interpreter, so on-device screenshot and interaction QA remains pending.

## Design.md visual language refinement (2026-11-17)

Applied the user's `Images/Design.md` specification across the desktop UI: near-black charcoal with a barely visible violet cast, 2?4% surface layering, softened contrast, rare muted-violet actions/focus, hairline borders, consistent 10/14/18/24px radii, quiet status colors, and restrained scrollbars. Updated the floating assistant and status bar to use the same palette. Kept the rounded app shell and session-first chat structure from the Kiro reference. Qt stylesheets do not provide true backdrop blur, so the glass effect is represented with opaque layered fills and subtle top-edge reflections.

Verification: Python syntax compilation and `git diff --check` passed. Visual launch QA is still pending because PySide6 is unavailable in the current interpreter.
