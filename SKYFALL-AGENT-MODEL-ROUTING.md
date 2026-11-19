# SKYFALL Agent Model Routing

Generated: 2026-11-19 19:54:30

These assignments use model IDs present in the user's OpenCode model list.
The Orchestrator uses MiMo V2.6 Flash to reduce coordination overhead.
The Architect is reserved for consequential design decisions and is not called routinely.
These are workload allocations, not benchmark claims or guaranteed quota isolation.

| Agent | Model | Intended workload |
|---|---|---|
| orchestrator | `opencode/mimo-v2.6-flash-free` | Fast, low-overhead coordination and delegation |
| explorer | `opencode/mimo-v2.6-flash-free` | Fast repository exploration |
| researcher | `opencode/deepseek-v4.1-flash-free` | Technical research |
| developer | `opencode/deepseek-v4.1-flash-free` | Implementation |
| debugger | `opencode/deepseek-v4.1-flash-free` | Root-cause analysis |
| tester | `opencode/nemotron-3.5-lightning-free` | Test execution and analysis |
| reviewer | `opencode/nemotron-3.5-super-vl-free` | Independent review |
| architect | `opencode/deepseek-v4.1-flash-free` | On-demand architecture decisions |
| security-auditor | `opencode/nemotron-3.5-super-vl-free` | Security review |

## Important

- OpenCode's model catalog does not prove quota status.
- This configuration does not implement automatic quota detection or automatic fallback.
- Change model IDs only to exact IDs exposed by `opencode models`.
- Start a new session after changing the default agent or model configuration.
- Existing sessions may retain their selected agent/model.

## Backup

Previous agent definitions and opencode.json were copied to:

`C:\Users\pranj\OneDrive\Documents\Skyfall(1)\Skyfall\.opencode\backups\Agent-Setup-20261119-195430`
