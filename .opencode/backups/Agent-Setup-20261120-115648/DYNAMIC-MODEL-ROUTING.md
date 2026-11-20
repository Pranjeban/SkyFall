# SKYFALL - MODEL ROUTING

## Current model

All specialist agents currently use the configured model:

`opencode/beam-free`

## Agent reasoning strategy

| Agent | Intended reasoning tier |
|---|---|
| orchestrator | Medium |
| explorer | Low |
| researcher | Medium |
| developer | High |
| debugger | High |
| tester | Medium |
| reviewer | High |
| architect | Xhigh |
| security-auditor | High |

These tiers are planning preferences, not verified provider capabilities.

## Model variants

Do not append `#low`, `#medium`, `#high` or `#xhigh` unless the provider exposes those exact variants.

Verify model availability using:

`opencode models`

## Default agent

`orchestrator`

## Agent files

`.opencode/agents/`