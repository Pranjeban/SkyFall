# SKYFALL - OpenCode Reasoning-Tier Routing

## Model

\$Model\ = opencode/beam-free

## Agent allocation

| Agent | Reasoning variant | Purpose |
|---|---|---|
| Orchestrator | Medium | Task classification and delegation |
| Explorer | Low | File discovery and repository reading |
| Researcher | Medium | Technical research |
| Developer | High | Implementation |
| Debugger | High | Root-cause investigation |
| Tester | Medium | Testing and validation |
| Reviewer | High | Independent review |
| Architect | Xhigh | Complex architecture |
| Security Auditor | High | Security analysis |

## Reasoning policy

Low:
Use for straightforward reading, searching and extraction.

Medium:
Use for coordination, research, analysis and ordinary testing.

High:
Use for implementation, debugging and code review.

Xhigh:
Reserve for complex architecture and high-impact engineering decisions.

## Escalation

The orchestrator should escalate when:
- Evidence indicates the current reasoning tier is insufficient.
- Repeated attempts fail.
- A significant architectural conflict exists.
- Data integrity or security is at risk.

Do not escalate automatically just because a task is long.

## Important

A reasoning variant is a model/provider-specific setting.
It is not a guaranteed token budget or a direct measurement of quality.

Validate actual behavior, availability and latency in OpenCode.