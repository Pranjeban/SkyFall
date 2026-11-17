# SKYFALL v0.9.2 — Account, Session, and Workspace Refinement

## Release intent

This milestone addresses the issues that block moving SKYFALL toward v1: a stable Power Platform connection, saved Microsoft accounts, clearer session management, and a calmer professional visual system.

## Power Platform connection

- Active application flows no longer require PAC CLI.
- Microsoft sign-in uses MSAL delegated OAuth with a public desktop app registration; SKYFALL does not accept or store a client secret.
- Account profiles and environment selection persist independently. Per-account token caches use MSAL Extensions platform protection (Windows DPAPI).
- Environment discovery uses Microsoft's Power Platform Environment Management API. Microsoft currently marks this endpoint preview, so API behavior can change: https://learn.microsoft.com/en-us/rest/api/power-platform/environmentmanagement/environments/list-environments-for-user
- Cloud-flow inventory uses the Dataverse Web API and only requests metadata. Microsoft's documented code path supports solution cloud flows and does not support My Flows: https://learn.microsoft.com/en-us/power-automate/manage-flows-with-code
- A tenant admin may need to register/consent a public client application with Power Platform API delegated environment read permission and Dynamics CRM `user_impersonation`. Configure its application (client) ID in SKYFALL Settings, then add a Microsoft account.

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

The smoke test now matches v0.9.2's tool set and direct OAuth setup. It performs an isolated child-process import preflight and reports import errors before MCP handshake, then formats connection/task-group failures more clearly. Run the test in the configured Python environment to complete end-to-end verification.

## MCP Azure login import repair

Restored the Azure MCP account-login tool that the server imports: new named isolated Azure profile login and existing-profile sign-in run as an authentication job. Test mode blocks external login. Regression coverage added for missing inputs and the test-mode guard.

## Unit regression count/string fixes

Updated v0.9.2 capability counts (20 total tools, 4 Power Platform discovery tools) and corrected the regex so literal parentheses in the client ID validation message match correctly.
