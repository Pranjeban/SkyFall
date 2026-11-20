# SKYFALL - OPENCODE MODEL ROUTING

Profile: Balanced
Default agent: orchestrator
Subagent depth: 1 (Orchestrator -> Specialist)
A NEW OpenCode session is required; existing sessions retain their selected agent.

## Agent model assignments

| Agent | Mode | Primary model | Weight | Backup models (priority order) |
|---|---|---|---:|---|
| intake | subagent | `opencode/nemotron-3.5-lightning-free` | 95/100 | `opencode/beam-free` (weight 85) |
| orchestrator | primary | `opencode/big-pickle` | 96/100 | `opencode/tidepool-alpha-free` (weight 88) |
| explorer | subagent | `opencode/beam-free` | 88/100 | `opencode/mimo-v2.6-flash-free` (weight 95) |
| visual-analyst | subagent | `opencode/nemotron-3.5-super-vl-free` | 98/100 | `opencode/big-pickle` (weight 78) |
| researcher | subagent | `opencode/big-pickle` | 89/100 | `opencode/longcat-2.5-free` (weight 96), `opencode/tidepool-alpha-free` (weight 91) |
| developer | subagent | `opencode/flint-40b-free` | 95/100 | `opencode/deepseek-v4.1-flash-free` (weight 97), `opencode/hy4-flash-free` (weight 86) |
| debugger | subagent | `opencode/iceman-free` | 90/100 | `opencode/flint-40b-free` (weight 96), `opencode/deepseek-v4.1-flash-free` (weight 94) |
| tester | subagent | `opencode/nemotron-3.5-lightning-free` | 92/100 | `opencode/hy4-flash-free` (weight 94), `opencode/mimo-v2.6-flash-free` (weight 89) |
| reviewer | subagent | `opencode/big-pickle` | 94/100 | `opencode/tidepool-alpha-free` (weight 95), `opencode/longcat-2.5-free` (weight 90) |
| architect | subagent | `opencode/longcat-2.5-free` | 95/100 | `opencode/big-pickle` (weight 97), `opencode/deepseek-v4.1-flash-free` (weight 90) |
| security-auditor | subagent | `opencode/nemotron-3.5-super-vl-free` | 90/100 | `opencode/deepseek-v4.1-flash-free` (weight 93), `opencode/iceman-free` (weight 95) |

## Execution policy

1. Orchestrator is the default primary agent and receives the user's request directly.
2. Intake is optional and is never required for normal requests.
3. Orchestrator MUST invoke specialists using the OpenCode subagent tool and exact agent IDs; mentioning an agent in prose is not delegation.
4. Orchestrator delegates only the minimum required specialist agents.
5. Simple requests should be handled directly without specialist delegation.
6. Agents must retrieve only task-relevant context and return concise evidence.

## Model availability and fallback

Only free OpenCode models from the supplied catalog are configured: Beam Free, Big Pickle, DeepSeek V4.1 Flash Free, Flint 40B Free, Hy4 Flash Free, Iceman Free, Inkling 2 Small Free, LongCat 2.5 Free, MiMo V2.6 Flash Free, Nemotron 3.5 Lightning Free, Nemotron 3.5 Super VL Free and Tidepool Alpha Free.
Weight is a 0-100 role-fit preference score used to order candidate models; it is not a live traffic split or benchmark score.
The first available candidate becomes the agent primary model; remaining available candidates are listed as backups in priority order.
OpenCode agent frontmatter stores one model per agent. Backups are documented/manual failover options; automatic runtime quota failover is not implemented by this installer.
If a model becomes unavailable or its free quota is exhausted, switch that agent using '/models' or rerun the installer after availability changes.

Do not assume that a model supports tool calling, vision, reasoning variants or a particular context window without verifying its catalog metadata.
Do not append #low, #medium, #high or #xhigh unless that exact variant is listed for the selected model.

## Agent files

.opencode/agents/"
    "
    

Only free OpenCode models are used. NVIDIA paid-tier models and Ollama models are excluded.
Model weights are heuristic role-fit priorities and should be tuned from actual task quality, latency and quota observations.
Nemotron Super VL Free is prioritized for visual analysis; do not assume other models support image input without checking their model metadata.