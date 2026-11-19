# SKYFALL Dynamic Model Routing

## Configured cloud models

| Tier | Model |
|---|---|
| Lightweight | opencode/mimo-v2.6-flash-free |
| Balanced | nvidia/deepseek-ai/deepseek-v4.1-flash |
| Advanced | nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b |

## Assignment

| Agent | Tier |
|---|---|
| Orchestrator | Balanced |
| Explorer | Lightweight |
| Researcher | Lightweight |
| Developer | Balanced |
| Debugger | Balanced |
| Tester | Lightweight |
| Reviewer | Balanced |
| Architect | Advanced |
| Security Auditor | Advanced |

## Routing strategy

Use lightweight models for predictable read-only work.

Use balanced models for regular engineering tasks.

Use advanced models only when deeper reasoning materially improves reliability.

Escalate when a task fails repeatedly, requires cross-module reasoning, or has significant security or architectural impact.

These assignments are initial defaults. Re-evaluate them against actual task quality, latency and provider usage limits.
