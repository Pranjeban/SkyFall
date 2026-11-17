# SKYFALL v1.0 — Intelligent Engineering Orchestration

**Status: active milestone definition / preview work.** The app version remains v0.9.2 until the v1.0 execution and validation requirements are complete.

## Product goal

A request such as “Find my Power Automate flow inventory script, inspect its requirements, connect to QA if necessary, execute it and generate the Excel report” should be decomposed into visible, reviewable stages:

1. Search enabled, approved workspaces.
2. Resolve a single existing script or ask the user to choose among candidates.
3. Inspect only permitted metadata for parameters, dependencies, language, and file freshness.
4. Resolve the exact requested environment; never guess ambiguous names such as QA/PROD.
5. Validate the selected Microsoft identity and access before work starts.
6. Build a concrete plan, inputs, expected output, and scope.
7. Ask for explicit approval at the boundary that needs it.
8. Run through a controlled, observable executor.
9. Validate exit status and expected report artifacts.
10. Deliver the report path and a concise result summary.

## v1.0 preview implemented in this working tree

- Replaced the Execution placeholder with a task-first Execution Center.
- Added local metadata search for indexed scripts and a safe summary of detected parameters/imports; no source is sent or displayed.
- Added explicit Microsoft account/tenant and target environment context. Tokens and secrets are never shown.
- Added ten labeled stages, a persistent progress bar, explicit approval, and a confirmed read-only Flow Inventory run route.
- The first wired route uses SKYFALL's existing Dataverse metadata inventory and local XLSX reporting. It does **not** execute the matched workspace script; arbitrary script execution still requires a purpose-built security boundary and validator.
- Updated the app theme toward light stone surfaces, slate text, and restrained blue/teal accents for contrast and long-session readability.

## Security boundaries before v1.0 release

- No automatically inferred or silently changed environment/profile.
- Show identity display name, username, tenant, environment, and permission state only. Never show a token, secret, or credential-cache value.
- Every operation that runs a user script or changes cloud resources requires explicit approval of the exact plan and inputs.
- Start with a constrained operation allowlist. Do not execute arbitrary shell strings or let Copilot invent command lines.
- Verify workspace approval, script path containment, indexed hash/freshness, parameters, dependencies, timeout, cancellation, output location, and report validation.
- A Python subprocess or PowerShell process under the user's account is not a security sandbox; design the execution boundary before enabling general script runs.

## Design reference notes

The visual direction borrows interaction patterns rather than copying artwork:

- Automation dashboards in Dribbble/Behance use a strong navigation hierarchy, calm card surfaces, and a single central work canvas: [Dribbble workflow builder](https://dribbble.com/shots/27802184-AI-Workflow-Builder-UI-Dark-SaaS-Automation-Dashboard), [Behance automation dashboard](https://www.behance.net/gallery/253989239/Nexora-Studio-Workflow-Automation-Dashboard).
- The orchestration page uses explicit task context and step status to keep approvals and account identity visible.
- For progress, the bar should move monotonically across the overall task; do not restart at every subtask. Show current status text and use indeterminate progress during unknown-duration network work, following [Microsoft Fluent 2 progress guidance](https://fluent2.microsoft.design/components/web/react/core/progressbar/usage) and [wait UX](https://fluent2.microsoft.design/wait-ux).

## Verification still required

- Run the full regression suite in the configured Windows Python environment.
- Exercise account refresh, ambiguous environment matching, expired authentication, denial, cancellation, partial errors, report validation, and recovery.
- Visually inspect the redesigned app at normal and compact window sizes on Windows.
- Do not label the application v1.0 until the above gates and the controlled execution path are complete.


## Visual direction update (2026-11-17)

The first light slate redesign was rejected by the user as visually poor. The replacement direction uses the supplied Kiro Crew screenshot and Kiro website as references: near-black graphite/plum foundations, muted lavender navigation, violet focus and primary actions, thin low-contrast borders, layered translucent card colors, and restrained mint/amber status colors. Chat, Markdown, floating assistant, account/profile dialogs, tables, and navigation now share that palette. The sidebar navigation surface is explicitly styled to prevent an unthemed black rectangle. This is a Qt glass-inspired layered treatment; it does not promise OS-level backdrop blur.

Visual validation still requires launching the desktop app on a machine with PySide6; the current workspace interpreter cannot render the UI.
