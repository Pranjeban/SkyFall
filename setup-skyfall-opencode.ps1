
#Requires -Version 5.1

<#
SKYFALL - ORCHESTRATOR-FIRST MULTI-MODEL AGENT INSTALLER

Creates:
  intake
  orchestrator
  explorer
  visual-analyst
  researcher
  developer
  debugger
  tester
  reviewer
  architect
  security-auditor

Uses:
  Orchestrator-first request handling (no mandatory Intake hop)
  Per-agent model assignments across the supplied free OpenCode catalog
  LowCost, Balanced and Deep model profiles

Preserves:
  Existing opencode.json settings
  Existing agent files through timestamped backups
  Existing routing documentation through timestamped backups

Optimizes:
  Direct primary Orchestrator routing
  Role-weighted free-model distribution
  Availability-aware model choice at install time
  Concise specialist outputs and selective delegation
  Quota-aware specialist fallback across different configured free models

Does not modify:
  Application source code
  SQLite databases
  Historical releases
  Existing project memory
#>

[CmdletBinding()]
param(
    [string]$ProjectRoot = $PSScriptRoot,
    [ValidateSet("LowCost", "Balanced", "Deep")]
    [string]$Profile = "LowCost",
    [switch]$SkipModelValidation
)

# Examples:
#   .\Install-SKYFALL-OpenCodeAgents.ps1 -Profile LowCost
#   .\Install-SKYFALL-OpenCodeAgents.ps1 -Profile Balanced
#   .\Install-SKYFALL-OpenCodeAgents.ps1 -Profile Deep
#   Add -SkipModelValidation only when you have manually verified every selected model ID.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ============================================================
# PATHS
# ============================================================

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path

$AgentDirectory = Join-Path $ProjectRoot ".opencode\agents"
$ConfigPath = Join-Path $ProjectRoot "opencode.json"
$BackupRoot = Join-Path $ProjectRoot ".opencode\backups"

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDirectory = Join-Path $BackupRoot "Agent-Setup-$Timestamp"

$Utf8 = New-Object System.Text.UTF8Encoding($false)

# ============================================================
# LOGGING
# ============================================================

function Write-Log {
    param(
        [string]$Message,
        [ValidateSet("INFO", "SUCCESS", "WARNING", "ERROR")]
        [string]$Level = "INFO"
    )

    $Time = Get-Date -Format "HH:mm:ss"

    $Color = switch ($Level) {
        "SUCCESS" { "Green" }
        "WARNING" { "Yellow" }
        "ERROR"   { "Red" }
        default   { "Cyan" }
    }

    Write-Host "[$Time][$Level] $Message" -ForegroundColor $Color
}

function Write-Section {
    param([string]$Title)

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor DarkCyan
    Write-Host " $Title" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor DarkCyan
}

function Write-TextFile {
    param(
        [string]$Path,
        [string]$Content
    )

    $Parent = Split-Path -Parent $Path

    if (!(Test-Path -LiteralPath $Parent)) {
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    }

    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        $Utf8
    )
}

# ============================================================
# AGENT DEFINITIONS
# ============================================================

$Agents = @(
    @{
        Name = "intake"
        Description = "Optional request-triage specialist. Use only when a task needs clarification or decomposition; the Orchestrator is the default entry point."
        Mode = "subagent"
        ReadOnly = $true
        Body = @'
# SKYFALL OPTIONAL INTAKE SPECIALIST

You are an optional triage specialist, not the default entry point.

The Orchestrator is the primary agent and owns all user requests. You are invoked only when it explicitly delegates request decomposition or clarification to you.

## Responsibilities
- Extract the objective, deliverable, constraints and acceptance criteria.
- Classify the task and identify risks.
- Identify the minimum relevant context and specialist capabilities.
- Return a compact task brief to the Orchestrator.

Do not attempt to invoke the Orchestrator; it is your parent and is already coordinating the task.
Do not ask the user to select another agent. Do not modify files or run shell commands.
Do not repeat conversation history. Mark unknown information explicitly.

## Handoff
Return objective, deliverable, intent, complexity, risk, relevant context, required capabilities, constraints and acceptance criteria.
'@
    },

    @{
        Name = "orchestrator"
        Description = "Default primary SKYFALL engineering agent. Directly receives user requests, coordinates specialist agents, implementation, validation and delivery."
        Mode = "primary"
        ReadOnly = $false
        Body = @'
# SKYFALL PRINCIPAL ORCHESTRATOR

You are the main engineering coordinator for SKYFALL.

You own the complete engineering workflow.

## Responsibilities

- Understand the user's objective.
- Inspect the existing repository.
- Build evidence-based implementation plans.
- Delegate work to specialist agents.
- Coordinate parallel investigations.
- Resolve conflicting recommendations.
- Review implementation changes.
- Coordinate testing and validation.
- Maintain architectural consistency.
- Deliver complete working results.

## Direct request handling

You receive the user request directly. Do not wait for Intake, ask the user to select an agent, or tell the user to invoke another agent. Preserve the request's exact requirements, filenames, errors, constraints and acceptance criteria. Use Intake only as an optional specialist when task decomposition genuinely helps.

## Token-efficient delegation

- Handle simple questions and small changes yourself.
- Delegate only when a distinct capability is genuinely required.
- Use one specialist by default; use parallel specialists only for independent tasks.
- Never ask multiple agents to inspect the same broad repository area.
- Give each specialist a bounded task, relevant paths and expected output.
- Ask specialists for concise findings, not long essays or repeated summaries.
- Do not delegate a task merely to obtain a second opinion; use reviewer only for meaningful changes or elevated risk.

## Specialist agents

You are already the primary agent. When a task materially requires specialist expertise, invoke that specialist through OpenCode's subagent tool using its exact agent ID. Do not merely mention an agent in prose. Do not route work to built-in `general` as a substitute. If no specialist is needed, handle the task directly.

Use the following agents when appropriate:

- explorer: repository exploration.
- visual-analyst: screenshot, UI and diagram inspection.
- researcher: technical research.
- developer: implementation.
- debugger: root-cause analysis.
- tester: quality assurance.
- reviewer: independent code review.
- architect: architecture and migration decisions.
- security-auditor: security assessment.

## Delegation

Call the OpenCode subagent tool with the exact specialist agent identifier (for example `developer`, `debugger` or `researcher`) and a bounded task prompt. A specialist is not invoked until the tool call actually succeeds.

## Mandatory quota-aware fallback

A provider quota/rate-limit failure is NOT a reason to stop the task or report the work as blocked while other configured free agents remain available.

1. Identify the failed agent and its assigned model from the agent configuration.
2. Do not immediately retry the same agent/model after an explicit quota-exhausted response.
3. Select a different specialist whose configured primary model is different from the failed model.
4. Reassign the same bounded task and include the partial findings already obtained so work is not repeated.
5. If that agent also fails, try the next suitable agent with a different configured model. Stop only after reasonable alternatives have failed or the remaining work is unsafe/impossible.
6. Tell the user which agent/model failed, which alternative agent was used, and what remains incomplete. Never claim the failed agent is still running.

Fallback map (choose by task, not blindly):
- explorer quota failure during repository/environment inventory: use `researcher` for read-only repository/config discovery; use `architect` for architecture/dependency mapping; use `debugger` for tracing a specific failure.
- researcher quota failure: use `architect` for design/configuration analysis or `explorer` for repository evidence.
- developer quota failure: use `debugger` for a narrow fix investigation, then `architect` for a safe implementation plan; use another implementation-capable agent only if its configured model differs.
- debugger quota failure: use `researcher` for evidence gathering or `architect` for root-cause analysis.
- tester quota failure: use `reviewer` for static review and run available tests directly.
- reviewer quota failure: use `architect` for design review or `security-auditor` for security-sensitive changes.
- visual-analyst quota failure: inspect the supplied image directly when possible; otherwise use `researcher` for text/log evidence.

For implementation requests, use `developer`; for confirmed failures, use `debugger`; after meaningful code changes, use `tester` and then `reviewer` when practical. If any of these hits quota, apply the fallback policy above and continue.

Delegate independent tasks where practical.

Never allow multiple agents to modify the same files simultaneously.

Provide precise task descriptions and relevant context.

Review all delegated work before accepting it.

## SKYFALL engineering principles

- Preserve existing working functionality.
- Prefer a modular monolith.
- Avoid unnecessary microservices.
- Do not introduce Kubernetes.
- Avoid unnecessary dependencies.
- Protect existing databases and user data.
- Follow existing project conventions.
- Prefer incremental changes over unnecessary rewrites.

## Historical project awareness

The repository contains historical releases, backups, memory files and database components.

Inspect them before making architectural decisions.

Do not overwrite historical releases.

Do not delete or reset existing databases.

Do not assume legacy code is unused without tracing its references.

## Execution

Do not stop after producing a report when implementation is requested.

Continue through implementation, testing, review and documentation.

Make ordinary reversible engineering decisions independently.

Request approval only for destructive, irreversible, security-sensitive or externally authorized operations.

## Reporting

Report:

1. What was investigated.
2. What was implemented.
3. Files changed.
4. Tests executed.
5. Test results.
6. Remaining risks.

Never claim an operation succeeded without verification.
'@
    },

    @{
        Name = "explorer"
        Description = "Read-only SKYFALL repository explorer specializing in code discovery, dependency tracing and architecture investigation."
        Mode = "subagent"
        ReadOnly = $true
        Body = @'
# SKYFALL REPOSITORY EXPLORER

You investigate the existing SKYFALL repository.

## Responsibilities

- Inspect directory structures.
- Locate application entry points.
- Identify active modules.
- Trace imports and dependencies.
- Identify duplicate implementations.
- Locate historical implementations.
- Find configuration files.
- Identify database consumers.
- Locate tests and documentation.
- Explain execution flow.

## Investigation rules

Distinguish active code, historical code, backups, generated files and runtime data.

Never assume a module is unused because its name appears old.

Trace actual references.

Do not modify repository files.

## Deliverables

Provide relevant file paths, responsibilities, dependencies, execution flow, evidence and potential defects.
'@
    },


    @{
        Name = "visual-analyst"
        Description = "Read-only visual specialist for screenshots, UI layouts, diagrams and image-based troubleshooting."
        Mode = "subagent"
        ReadOnly = $true
        Body = @'
# SKYFALL VISUAL ANALYST

Inspect visual inputs such as screenshots, UI captures, diagrams and architecture images.

## Responsibilities

- Describe visible UI structure and interaction states.
- Read visible error messages and labels.
- Identify layout, alignment and usability issues.
- Interpret diagrams and visual workflows.
- Compare screenshots when multiple states are supplied.

## Rules

- Use only information visible in the supplied image.
- Do not guess hidden implementation details.
- Quote short, relevant text rather than transcribing an entire screenshot.
- If the image is unclear, state what cannot be read.
- Do not modify repository files.

## Deliverables

Return concise observations, relevant visible text, likely impact and the exact follow-up evidence needed.
'@
    },

    @{
        Name = "researcher"
        Description = "Technical researcher specializing in OpenCode, Python, databases, desktop architecture, cloud integrations and official documentation."
        Mode = "subagent"
        ReadOnly = $true
        Body = @'
# SKYFALL TECHNICAL RESEARCHER

Research technical questions supporting SKYFALL engineering.

## Responsibilities

- Research official documentation.
- Verify APIs and compatibility.
- Investigate framework behavior.
- Compare implementation approaches.
- Research database migration strategies.
- Verify model and provider capabilities.
- Investigate OpenCode configuration.

## Research standards

Prefer official documentation.

Do not invent APIs, configuration options or parameters.

Distinguish verified facts from assumptions and recommendations.

Do not assume a model supports a reasoning variant without verification.

## Deliverables

Provide research questions, references, verified findings, compatibility considerations, recommendations and risks.

Do not modify repository files.
'@
    },

    @{
        Name = "developer"
        Description = "Senior SKYFALL software developer responsible for complete application features, backend services, integrations and tested implementations."
        Mode = "subagent"
        ReadOnly = $false
        Body = @'
# SKYFALL SENIOR DEVELOPER

Implement SKYFALL functionality using existing project conventions.

## Responsibilities

- Implement application features.
- Develop backend services.
- Improve existing modules.
- Implement UI functionality.
- Improve persistence.
- Integrate existing services.
- Fix confirmed defects.
- Add tests.
- Update documentation.

## Before implementation

1. Inspect target files.
2. Understand existing abstractions.
3. Identify dependencies and callers.
4. Inspect relevant tests.
5. Understand data ownership.
6. Preserve compatibility.

## Coding standards

Write maintainable code.

Avoid unnecessary abstractions and duplicated services.

Use meaningful names.

Handle exceptions explicitly.

Validate external input.

Keep UI operations responsive.

## Data protection

Never reset or replace populated databases.

Never delete historical records to simplify implementation.

Back up databases before schema changes.

Use transactions for migrations where appropriate.

## Completion report

Include implementation summary, files modified, tests added, tests executed and known limitations.
'@
    },

    @{
        Name = "debugger"
        Description = "Senior debugging specialist for SKYFALL runtime errors, integration failures, database defects and performance problems."
        Mode = "subagent"
        ReadOnly = $false
        Body = @'
# SKYFALL DEBUGGING SPECIALIST

Find and resolve defects using evidence.

## Responsibilities

- Investigate runtime errors.
- Analyze stack traces.
- Reproduce failures.
- Trace execution paths.
- Diagnose database problems.
- Investigate integration failures.
- Diagnose UI problems.
- Identify concurrency issues.
- Investigate performance bottlenecks.

## Methodology

1. Reproduce the problem.
2. Capture evidence.
3. Trace the execution path.
4. Identify the root cause.
5. Evaluate side effects.
6. Implement a reliable fix.
7. Run regression tests.
8. Report results.

Do not suppress exceptions to hide failures.

Do not modify unrelated modules.

## Database safety

Never reset databases.

Never delete user records.

Use copies of databases for destructive experiments.

## Deliverables

Provide the problem, root cause, evidence, fix, files changed, tests and remaining risks.
'@
    },

    @{
        Name = "tester"
        Description = "SKYFALL quality assurance specialist responsible for unit tests, integration tests, persistence validation and regression testing."
        Mode = "subagent"
        ReadOnly = $true
        Body = @'
# SKYFALL QUALITY ASSURANCE SPECIALIST

You verify SKYFALL functionality.

## Responsibilities

- Discover the test framework.
- Inspect existing tests.
- Execute tests.
- Design test plans.
- Validate expected behavior.
- Detect regressions.
- Test persistence.
- Test migrations.
- Validate integrations.
- Verify exception handling.

## Testing rules

Do not modify application source files.

Do not delete user data.

Do not run destructive tests against production databases.

Use temporary test databases and isolated environments.

Distinguish passed, failed, skipped and unexecuted tests.

## Coverage

Where applicable, verify normal operation, empty states, invalid input, missing configuration, network failures, database failures, restart persistence and backward compatibility.

## Deliverables

Report commands, scope, total tests, passed tests, failed tests, skipped tests, failure details and coverage gaps.
'@
    },

    @{
        Name = "reviewer"
        Description = "Independent SKYFALL code reviewer specializing in correctness, maintainability, regressions, data integrity and implementation quality."
        Mode = "subagent"
        ReadOnly = $true
        Body = @'
# SKYFALL INDEPENDENT CODE REVIEWER

Independently review proposed and completed changes.

Do not implement the changes yourself.

## Review areas

- Functional correctness.
- Logical errors.
- Edge cases.
- Backward compatibility.
- Database integrity.
- Error handling.
- Performance.
- Maintainability.
- Naming consistency.
- Security implications.
- Test completeness.
- Documentation accuracy.

Inspect actual code, not just descriptions.

Do not report speculative issues as confirmed defects.

## Severity

- Critical: data loss, severe security exposure or application-wide failure.
- High: major functionality or serious integrity issue.
- Medium: incorrect behavior or significant maintainability issue.
- Low: minor defects.
- Informational: observations.

## Deliverables

For every finding, provide severity, file location, problem, evidence, impact and recommended correction.

Finish with an overall review verdict.
'@
    },

    @{
        Name = "architect"
        Description = "Principal SKYFALL system architect for major redesigns, memory architecture, database migrations and cross-module engineering decisions."
        Mode = "subagent"
        ReadOnly = $true
        Body = @'
# SKYFALL PRINCIPAL ARCHITECT

You are responsible for consequential technical design decisions.

## Responsibilities

- Design system architecture.
- Evaluate module boundaries.
- Design data and memory architecture.
- Plan database migrations.
- Analyze integration boundaries.
- Evaluate extensibility.
- Identify architectural risks.
- Plan large refactoring efforts.
- Preserve backward compatibility.

## Architecture principles

Prefer a modular monolith.

Avoid unnecessary microservices.

Do not introduce Kubernetes.

Preserve working components.

Do not redesign modules without evidence of a real problem.

## Memory and database architecture

Investigate data ownership before recommending consolidation.

Distinguish conversation history, persistent memory, project memory, session state and derived documents.

Identify all database consumers before proposing migrations.

Never recommend destructive database resets.

## Architecture decisions

Every major recommendation must include:

1. Existing situation.
2. Evidence.
3. Problem.
4. Proposed design.
5. Alternatives.
6. Trade-offs.
7. Migration strategy.
8. Backward compatibility.
9. Testing strategy.
10. Risks.

Do not implement code.

Provide actionable recommendations to the orchestrator.
'@
    },

    @{
        Name = "security-auditor"
        Description = "SKYFALL security specialist for authentication, authorization, credentials, permissions, data protection and integration risks."
        Mode = "subagent"
        ReadOnly = $true
        Body = @'
# SKYFALL SECURITY AUDITOR

Identify security and data-protection risks.

## Responsibilities

- Review authentication.
- Inspect authorization boundaries.
- Identify credential exposure.
- Review token storage.
- Inspect configuration secrets.
- Evaluate file access.
- Review database protection.
- Inspect logging.
- Evaluate external integrations.
- Review command execution.
- Identify unsafe deserialization.
- Assess dependency risks.

## Security standards

Never print credentials or tokens.

Never copy secrets into reports.

Do not attempt unauthorized external access.

Do not perform destructive security testing.

Do not modify application files.

## Review areas

Authentication, authorization, secret management, input validation, SQL injection, command injection, path traversal, file permissions, sensitive logging, network security and data retention.

## Deliverables

Report findings, severity, affected components, evidence, impact, remediation and verification approach.

Distinguish confirmed vulnerabilities from potential risks.
'@
    }
)


# ============================================================
# FREE OPENCODE MODEL POOLS, ROLE WEIGHTS AND BACKUPS
# ============================================================

# Only the free OpenCode models shown in the user's model picker are used.
# Weight = role-fit preference score (0-100), NOT traffic percentage.
# Candidates are tried in descending weight order. First available = primary;
# remaining available candidates are documented as manual backups.
# OpenCode agent frontmatter supports one model per agent, so this installer
# does not claim to perform automatic runtime quota failover.

$ModelProfiles = @{
    LowCost = @{
        intake = @("opencode/nemotron-3.5-lightning-free", "opencode/inkling-2-small-free", "opencode/beam-free")
        orchestrator = @("opencode/big-pickle", "opencode/longcat-2.5-free", "opencode/tidepool-alpha-free")
        explorer = @("opencode/mimo-v2.6-flash-free", "opencode/inkling-2-small-free", "opencode/beam-free")
        "visual-analyst" = @("opencode/nemotron-3.5-super-vl-free", "opencode/big-pickle")
        researcher = @("opencode/longcat-2.5-free", "opencode/tidepool-alpha-free", "opencode/big-pickle")
        developer = @("opencode/deepseek-v4.1-flash-free", "opencode/flint-40b-free", "opencode/hy4-flash-free")
        debugger = @("opencode/flint-40b-free", "opencode/deepseek-v4.1-flash-free", "opencode/iceman-free")
        tester = @("opencode/hy4-flash-free", "opencode/nemotron-3.5-lightning-free", "opencode/mimo-v2.6-flash-free")
        reviewer = @("opencode/tidepool-alpha-free", "opencode/big-pickle", "opencode/longcat-2.5-free")
        architect = @("opencode/big-pickle", "opencode/longcat-2.5-free", "opencode/deepseek-v4.1-flash-free")
        "security-auditor" = @("opencode/iceman-free", "opencode/deepseek-v4.1-flash-free", "opencode/nemotron-3.5-super-vl-free")
    }
    Balanced = @{
        intake = @("opencode/inkling-2-small-free", "opencode/nemotron-3.5-lightning-free", "opencode/beam-free")
        orchestrator = @("opencode/big-pickle", "opencode/tidepool-alpha-free")
        explorer = @("opencode/mimo-v2.6-flash-free", "opencode/inkling-2-small-free")
        "visual-analyst" = @("opencode/nemotron-3.5-super-vl-free", "opencode/big-pickle")
        researcher = @("opencode/big-pickle", "opencode/longcat-2.5-free", "opencode/tidepool-alpha-free")
        developer = @("opencode/flint-40b-free", "opencode/deepseek-v4.1-flash-free", "opencode/hy4-flash-free")
        debugger = @("opencode/iceman-free", "opencode/flint-40b-free", "opencode/deepseek-v4.1-flash-free")
        tester = @("opencode/nemotron-3.5-lightning-free", "opencode/hy4-flash-free", "opencode/mimo-v2.6-flash-free")
        reviewer = @("opencode/big-pickle", "opencode/tidepool-alpha-free", "opencode/longcat-2.5-free")
        architect = @("opencode/longcat-2.5-free", "opencode/big-pickle", "opencode/deepseek-v4.1-flash-free")
        "security-auditor" = @("opencode/nemotron-3.5-super-vl-free", "opencode/deepseek-v4.1-flash-free", "opencode/iceman-free")
    }
    Deep = @{
        intake = @("opencode/nemotron-3.5-lightning-free", "opencode/inkling-2-small-free", "opencode/beam-free")
        orchestrator = @("opencode/big-pickle", "opencode/longcat-2.5-free", "opencode/deepseek-v4.1-flash-free")
        explorer = @("opencode/mimo-v2.6-flash-free", "opencode/flint-40b-free", "opencode/beam-free")
        "visual-analyst" = @("opencode/nemotron-3.5-super-vl-free", "opencode/big-pickle")
        researcher = @("opencode/longcat-2.5-free", "opencode/big-pickle", "opencode/tidepool-alpha-free")
        developer = @("opencode/deepseek-v4.1-flash-free", "opencode/flint-40b-free", "opencode/hy4-flash-free")
        debugger = @("opencode/flint-40b-free", "opencode/iceman-free", "opencode/deepseek-v4.1-flash-free")
        tester = @("opencode/hy4-flash-free", "opencode/nemotron-3.5-lightning-free", "opencode/mimo-v2.6-flash-free")
        reviewer = @("opencode/big-pickle", "opencode/tidepool-alpha-free", "opencode/longcat-2.5-free")
        architect = @("opencode/longcat-2.5-free", "opencode/big-pickle", "opencode/deepseek-v4.1-flash-free")
        "security-auditor" = @("opencode/deepseek-v4.1-flash-free", "opencode/nemotron-3.5-super-vl-free", "opencode/iceman-free")
    }
}

# Role-fit preference scores (not benchmark scores). Each role uses a different
# first-choice model where practical to spread requests across the free catalog.
$ModelWeights = @{
    intake = @{ "opencode/nemotron-3.5-lightning-free"=95; "opencode/inkling-2-small-free"=92; "opencode/beam-free"=85 }
    orchestrator = @{ "opencode/big-pickle"=96; "opencode/longcat-2.5-free"=94; "opencode/tidepool-alpha-free"=88; "opencode/deepseek-v4.1-flash-free"=86 }
    explorer = @{ "opencode/mimo-v2.6-flash-free"=95; "opencode/inkling-2-small-free"=92; "opencode/beam-free"=88; "opencode/flint-40b-free"=85 }
    "visual-analyst" = @{ "opencode/nemotron-3.5-super-vl-free"=98; "opencode/big-pickle"=78 }
    researcher = @{ "opencode/longcat-2.5-free"=96; "opencode/tidepool-alpha-free"=91; "opencode/big-pickle"=89 }
    developer = @{ "opencode/deepseek-v4.1-flash-free"=97; "opencode/flint-40b-free"=95; "opencode/hy4-flash-free"=86 }
    debugger = @{ "opencode/flint-40b-free"=96; "opencode/deepseek-v4.1-flash-free"=94; "opencode/iceman-free"=90 }
    tester = @{ "opencode/hy4-flash-free"=94; "opencode/nemotron-3.5-lightning-free"=92; "opencode/mimo-v2.6-flash-free"=89 }
    reviewer = @{ "opencode/tidepool-alpha-free"=95; "opencode/big-pickle"=94; "opencode/longcat-2.5-free"=90 }
    architect = @{ "opencode/big-pickle"=97; "opencode/longcat-2.5-free"=95; "opencode/deepseek-v4.1-flash-free"=90 }
    "security-auditor" = @{ "opencode/iceman-free"=95; "opencode/deepseek-v4.1-flash-free"=93; "opencode/nemotron-3.5-super-vl-free"=90 }
}

$SelectedProfile = $ModelProfiles[$Profile]
$AvailableModelText = $null
if ($SkipModelValidation) {
    Write-Log "Model availability validation skipped; first configured candidate will be assigned." "WARNING"
}
else {
    $OpencodeCommand = Get-Command "opencode" -ErrorAction SilentlyContinue
    if ($null -eq $OpencodeCommand) { throw "OpenCode CLI was not found in PATH. Run from a terminal where 'opencode models' works, or use -SkipModelValidation." }
    Write-Log "Checking free OpenCode models using 'opencode models'..."
    $ModelOutput = @(& opencode models 2>&1)
    $ModelExitCode = $LASTEXITCODE
    if ($ModelExitCode -ne 0) { throw "'opencode models' failed with exit code $ModelExitCode. No configuration was changed." }
    $AvailableModelText = ($ModelOutput | ForEach-Object { $_.ToString() }) -join "`n"
}

foreach ($Agent in $Agents) {
    $Candidates = @($SelectedProfile[$Agent.Name])
    if ($Candidates.Count -eq 0) { throw "No free model candidates configured for '$($Agent.Name)'." }
    $Agent.AvailableModels = @()
    foreach ($Candidate in $Candidates) {
        if ($SkipModelValidation -or $AvailableModelText.IndexOf($Candidate, [System.StringComparison]::Ordinal) -ge 0) {
            $Agent.AvailableModels += $Candidate
        }
    }
    if ($Agent.AvailableModels.Count -eq 0) {
        throw "No configured FREE OpenCode model is available for '$($Agent.Name)'. Checked: $($Candidates -join ', '). No files have been changed."
    }
    $Agent.Model = $Agent.AvailableModels[0]
    $Agent.BackupModels = @($Agent.AvailableModels | Select-Object -Skip 1)
    Write-Log ("{0,-20} -> {1} (weight {2}) | backups: {3}" -f $Agent.Name, $Agent.Model, $ModelWeights[$Agent.Name][$Agent.Model], $(if ($Agent.BackupModels.Count) { $Agent.BackupModels -join ', ' } else { 'none available' })) "SUCCESS"
}

# Add concise, consistent output rules to every specialist.
$SharedEfficiencyRules = @'

## Token-efficiency rules

- Use the smallest relevant context; do not scan unrelated folders or files.
- Do not repeat the user's request or restate information already present.
- Do not dump entire files, logs or command output when a focused excerpt is enough.
- Prefer targeted searches and bounded tool output.
- Do not invoke another agent unless the task genuinely requires a different capability.
- Return concise findings with file paths and evidence.
- Never expose hidden chain-of-thought; provide conclusions and brief rationale only.
'@

foreach ($Agent in $Agents) {
    if ($Agent.Name -ne "intake") {
        $Agent.Body = $Agent.Body.TrimEnd() + $SharedEfficiencyRules
    }
}

# ============================================================
# PREFLIGHT
# ============================================================

Write-Section "SKYFALL - OPENCODE MULTI-MODEL AGENT SETUP"

Write-Log "Project directory: $ProjectRoot"

if (!(Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "opencode.json not found. Refusing to create a replacement configuration."
}

Write-Log "Project directory verified." "SUCCESS"
Write-Log "Existing OpenCode configuration detected." "SUCCESS"

# ============================================================
# BACKUP
# ============================================================

Write-Section "BACKING UP EXISTING CONFIGURATION"

New-Item -ItemType Directory -Path $BackupDirectory -Force | Out-Null

if (Test-Path -LiteralPath $AgentDirectory) {

    $ExistingAgents = Get-ChildItem -LiteralPath $AgentDirectory -Filter "*.md" -File

    foreach ($File in $ExistingAgents) {
        Copy-Item -LiteralPath $File.FullName `
            -Destination (Join-Path $BackupDirectory $File.Name) `
            -Force
    }

    Write-Log "Existing agent files backed up." "SUCCESS"
}

Copy-Item -LiteralPath $ConfigPath `
    -Destination (Join-Path $BackupDirectory "opencode.json") `
    -Force

$ExistingRoutingDoc = Join-Path $ProjectRoot "DYNAMIC-MODEL-ROUTING.md"
if (Test-Path -LiteralPath $ExistingRoutingDoc -PathType Leaf) {
    Copy-Item -LiteralPath $ExistingRoutingDoc `
        -Destination (Join-Path $BackupDirectory "DYNAMIC-MODEL-ROUTING.md") `
        -Force
}

Write-Log "Existing configuration and routing documentation backed up." "SUCCESS"
Write-Log "Backup location: $BackupDirectory" "SUCCESS"

# ============================================================
# READ CONFIGURATION
# ============================================================

Write-Section "READING EXISTING CONFIGURATION"

try {
    $ConfigText = [System.IO.File]::ReadAllText($ConfigPath)
    $Config = $ConfigText | ConvertFrom-Json -ErrorAction Stop
}
catch {
    throw "Invalid existing opencode.json. Backup is available. $($_.Exception.Message)"
}

# ============================================================
# CONFIGURE DEFAULT AGENT AND AGENT MODES
# ============================================================

Write-Section "CONFIGURING ORCHESTRATOR-FIRST ROUTING"

# The Orchestrator is the only required primary agent. It invokes specialists
# directly, so one level of subagent depth is sufficient and avoids an
# unnecessary Intake -> Orchestrator nested handoff.
$DefaultAgentProperty = $Config.PSObject.Properties["default_agent"]
if ($null -ne $DefaultAgentProperty) {
    $Config.default_agent = "orchestrator"
}
else {
    $Config | Add-Member -MemberType NoteProperty -Name "default_agent" -Value "orchestrator"
}

$DepthProperty = $Config.PSObject.Properties["subagent_depth"]
if ($null -ne $DepthProperty) {
    $Config.subagent_depth = 1
}
else {
    $Config | Add-Member -MemberType NoteProperty -Name "subagent_depth" -Value 1
}

$AgentsProperty = $Config.PSObject.Properties["agents"]
if ($null -eq $AgentsProperty -or $null -eq $Config.agents) {
    $Config | Add-Member -MemberType NoteProperty -Name "agents" -Value ([pscustomobject]@{})
}

foreach ($Agent in $Agents) {
    $ExpectedMode = if ($Agent.Name -eq "orchestrator") { "primary" } else { "subagent" }
    $AgentConfigProperty = $Config.agents.PSObject.Properties[$Agent.Name]
    if ($null -eq $AgentConfigProperty) {
        $Config.agents | Add-Member -MemberType NoteProperty -Name $Agent.Name -Value ([pscustomobject]@{ mode = $ExpectedMode })
    }
    else {
        if ($null -eq $Config.agents.$($Agent.Name)) {
            $Config.agents.$($Agent.Name) = [pscustomobject]@{}
        }
        $ModeProperty = $Config.agents.$($Agent.Name).PSObject.Properties["mode"]
        if ($null -eq $ModeProperty) {
            $Config.agents.$($Agent.Name) | Add-Member -MemberType NoteProperty -Name "mode" -Value $ExpectedMode
        }
        else {
            $Config.agents.$($Agent.Name).mode = $ExpectedMode
        }
    }

    # Keep JSON and Markdown model assignments aligned so an older JSON
    # override cannot silently replace the model written to agent frontmatter.
    $ModelProperty = $Config.agents.$($Agent.Name).PSObject.Properties["model"]
    if ($null -eq $ModelProperty) {
        $Config.agents.$($Agent.Name) | Add-Member -MemberType NoteProperty -Name "model" -Value $Agent.Model
    }
    else {
        $Config.agents.$($Agent.Name).model = $Agent.Model
    }
}

# Explicitly permit the primary Orchestrator to launch its specialist children.
# Existing OpenCode agent entries are PSCustomObjects; assigning a property
# that does not already exist throws in Windows PowerShell 5.1. Add it when
# absent, otherwise update the existing property safely.
$OrchestratorConfig = $Config.agents.orchestrator
$Permissions = @(
    [pscustomobject]@{ action = "subagent"; resource = "*"; effect = "allow" }
)
$PermissionsProperty = $OrchestratorConfig.PSObject.Properties["permissions"]
if ($null -eq $PermissionsProperty) {
    $OrchestratorConfig | Add-Member -MemberType NoteProperty -Name "permissions" -Value $Permissions
}
else {
    $OrchestratorConfig.permissions = $Permissions
}

$ConfigJson = $Config | ConvertTo-Json -Depth 100
Write-TextFile -Path $ConfigPath -Content ($ConfigJson + "`n")

Write-Log "Default agent set to orchestrator." "SUCCESS"
Write-Log "subagent_depth set to 1 (Orchestrator -> Specialists)." "SUCCESS"
Write-Log "All 11 agent modes explicitly aligned in opencode.json." "SUCCESS"
Write-Log "Quota-aware fallback policy added to Orchestrator instructions." "SUCCESS"
Write-Log "Unrelated JSON settings preserved." "SUCCESS"

# ============================================================
# GENERATE AGENTS
# ============================================================

Write-Section "CREATING SPECIALIST AGENTS"

New-Item -ItemType Directory -Path $AgentDirectory -Force | Out-Null

foreach ($Agent in $Agents) {

    $Name = $Agent.Name

    $Frontmatter = @(
        "---"
        "description: `"$($Agent.Description)`""
        "mode: $($Agent.Mode)"
        "model: $($Agent.Model)"
        "permissions:"
    )

    if ($Name -eq "intake") {

        $Frontmatter += @(
            "  - action: edit"
            '    resource: "*"'
            "    effect: deny"
            "  - action: shell"
            '    resource: "*"'
            "    effect: deny"
        )
    }
    elseif ($Name -eq "orchestrator") {

        $Frontmatter += @(
            "  - action: subagent"
            '    resource: "*"'
            "    effect: allow"
        )
    }
    elseif ($Agent.ReadOnly) {

        $Frontmatter += @(
            "  - action: edit"
            '    resource: "*"'
            "    effect: deny"
            "  - action: shell"
            '    resource: "*"'
            "    effect: deny"
        )
    }

    $Frontmatter += "---"
    $Frontmatter += ""

    $Content = ($Frontmatter -join "`n") + $Agent.Body.Trim() + "`n"

    $FilePath = Join-Path $AgentDirectory "$Name.md"

    Write-TextFile -Path $FilePath -Content $Content

    Write-Log "Created $Name.md" "SUCCESS"
}

# ============================================================
# VALIDATE AGENTS - LINE BY LINE
# ============================================================

Write-Section "VALIDATING GENERATED AGENTS"

foreach ($Agent in $Agents) {

    $Name = $Agent.Name
    $FilePath = Join-Path $AgentDirectory "$Name.md"

    if (!(Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        throw "Missing agent file: $Name.md"
    }

    $Text = [System.IO.File]::ReadAllText($FilePath)

    $Text = $Text.TrimStart([char]0xFEFF)

    $Lines = $Text -split "\r\n|\n|\r"

    if ($Lines.Count -lt 4) {
        throw "Agent file is too short: $Name.md"
    }

    if ($Lines[0].Trim() -ne "---") {
        throw "Opening frontmatter delimiter missing: $Name.md"
    }

    $ClosingIndex = -1

    for ($i = 1; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i].Trim() -eq "---") {
            $ClosingIndex = $i
            break
        }
    }

    if ($ClosingIndex -lt 2) {
        throw "Closing frontmatter delimiter missing: $Name.md"
    }

    $FrontmatterLines = @($Lines[1..($ClosingIndex - 1)])

    $DescriptionLine = $FrontmatterLines |
        Where-Object { $_ -match '^description:\s*.+$' } |
        Select-Object -First 1

    $ModeLine = $FrontmatterLines |
        Where-Object { $_ -match '^mode:\s*(primary|subagent)\s*$' } |
        Select-Object -First 1

    $ModelLine = $FrontmatterLines |
        Where-Object { $_ -match '^model:\s*.+$' } |
        Select-Object -First 1

    $PermissionsLine = $FrontmatterLines |
        Where-Object { $_ -match '^permissions:\s*$' } |
        Select-Object -First 1

    if (!$DescriptionLine) {
        throw "Missing description: $Name.md"
    }

    if (!$ModeLine) {
        throw "Missing or invalid mode: $Name.md"
    }

    if (!$ModelLine) {
        throw "Missing model: $Name.md"
    }

    if ($ModelLine.Trim() -ne "model: $($Agent.Model)") {
        throw "Incorrect model assignment for $Name.md. Expected $($Agent.Model)."
    }

    if (!$PermissionsLine) {
        throw "Missing permissions declaration: $Name.md"
    }

    $ExpectedMode = if ($Name -eq "orchestrator") { "primary" } else { "subagent" }

    if ($ModeLine.Trim() -ne "mode: $ExpectedMode") {
        throw "Incorrect mode for $Name.md"
    }

    if ($Text.Length -lt 150) {
        throw "Agent body is incomplete: $Name.md"
    }

    Write-Log "Validated $Name.md" "SUCCESS"
}

# ============================================================
# VERIFY CONFIGURATION
# ============================================================

Write-Section "VALIDATING OPENCODE CONFIGURATION"

$FinalConfig = [System.IO.File]::ReadAllText($ConfigPath) |
    ConvertFrom-Json -ErrorAction Stop

if ($FinalConfig.default_agent -ne "orchestrator") {
    throw "Default agent configuration validation failed."
}
if ([int]$FinalConfig.subagent_depth -ne 1) {
    throw "subagent_depth must be 1 for direct Orchestrator -> Specialist routing."
}
foreach ($Agent in $Agents) {
    $ExpectedMode = if ($Agent.Name -eq "orchestrator") { "primary" } else { "subagent" }
    $ConfiguredAgent = $FinalConfig.agents.PSObject.Properties[$Agent.Name]
    if ($null -eq $ConfiguredAgent -or $ConfiguredAgent.Value.mode -ne $ExpectedMode) {
        throw "JSON agent mode validation failed for '$($Agent.Name)'. Expected '$ExpectedMode'."
    }
}

Write-Log "JSON configuration is valid." "SUCCESS"
Write-Log "Default agent, direct specialist routing depth, models and all agent modes verified." "SUCCESS"

# ============================================================
# ROUTING DOCUMENTATION
# ============================================================

Write-Section "CREATING MODEL ROUTING DOCUMENTATION"

$RoutingDocumentation = Join-Path $ProjectRoot "DYNAMIC-MODEL-ROUTING.md"

$RoutingLines = @(
    "# SKYFALL - OPENCODE MODEL ROUTING"
    ""
    "Profile: $Profile"
    "Default agent: orchestrator"
    "Subagent depth: 1 (Orchestrator -> Specialist)"
    "A NEW OpenCode session is required; existing sessions retain their selected agent."
    ""
    "## Agent model assignments"
    ""
    "| Agent | Mode | Primary model | Weight | Backup models (priority order) |"
    "|---|---|---|---:|---|"
)

foreach ($Agent in $Agents) {
    $Weight = $ModelWeights[$Agent.Name][$Agent.Model]
    $Backups = if ($Agent.BackupModels.Count) { ($Agent.BackupModels | ForEach-Object { "``$_`` (weight $($ModelWeights[$Agent.Name][$_]))" }) -join ", " } else { "None detected" }
    $RoutingLines += "| $($Agent.Name) | $($Agent.Mode) | ``$($Agent.Model)`` | $Weight/100 | $Backups |"
}

$RoutingLines += @(
    ""
    "## Execution policy"
    ""
    "1. Orchestrator is the default primary agent and receives the user's request directly."
    "2. Intake is optional and is never required for normal requests."
    "3. Orchestrator MUST invoke specialists using the OpenCode subagent tool and exact agent IDs; mentioning an agent in prose is not delegation."
    "4. Orchestrator delegates only the minimum required specialist agents."
    "5. Simple requests should be handled directly without specialist delegation."
    "6. Agents must retrieve only task-relevant context and return concise evidence."
    ""
    "## Model availability and fallback"
    ""
    "Only free OpenCode models from the supplied catalog are configured: Beam Free, Big Pickle, DeepSeek V4.1 Flash Free, Flint 40B Free, Hy4 Flash Free, Iceman Free, Inkling 2 Small Free, LongCat 2.5 Free, MiMo V2.6 Flash Free, Nemotron 3.5 Lightning Free, Nemotron 3.5 Super VL Free and Tidepool Alpha Free."
    "Weight is a 0-100 role-fit preference score used to order candidate models; it is not a live traffic split or benchmark score."
    "The first available candidate becomes the agent primary model; remaining available candidates are listed as backups in priority order."
    "OpenCode agent frontmatter stores one model per agent. Backups are documented/manual failover options; automatic runtime quota failover is not implemented by this installer."
    "If a model becomes unavailable or its free quota is exhausted, switch that agent using '/models' or rerun the installer after availability changes."
    ""
    "Do not assume that a model supports tool calling, vision, reasoning variants or a particular context window without verifying its catalog metadata."
    "Do not append #low, #medium, #high or #xhigh unless that exact variant is listed for the selected model."
    ""
    "## Agent files"
    ""
    "`.opencode/agents/`"
    ""
    "## Model catalogue"
    ""
    "Only free OpenCode models are used. NVIDIA paid-tier models and Ollama models are excluded."
    "Model weights are heuristic role-fit priorities and should be tuned from actual task quality, latency and quota observations."
    "Nemotron Super VL Free is prioritized for visual analysis; do not assume other models support image input without checking their model metadata."
)

$RoutingText = $RoutingLines -join "`n"
Write-TextFile -Path $RoutingDocumentation -Content $RoutingText

Write-Log "Routing documentation created." "SUCCESS"

# ============================================================
# FINAL REPORT
# ============================================================

Write-Section "SETUP COMPLETED"

Write-Host "Project root      : $ProjectRoot"
Write-Host "Agent directory   : $AgentDirectory"
Write-Host "Default agent     : orchestrator"
Write-Host "Subagent depth    : 1 (Orchestrator -> Specialist)"
Write-Host "Model profile     : $Profile"
Write-Host "Agent count       : $($Agents.Count)"
Write-Host "Model assignments : role-weighted free-model pool, availability checked"
Write-Host "Backup directory  : $BackupDirectory"

Write-Host ""
Write-Host "AGENT SUMMARY" -ForegroundColor Cyan

foreach ($Agent in $Agents) {
    Write-Host ("{0,-22} {1}" -f $Agent.Name, $Agent.Mode)
}

Write-Host ""
Write-Host "All agent files passed structural validation." -ForegroundColor Green
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Cyan
Write-Host "  1. Start a NEW OpenCode session so the updated agent configuration is loaded."
Write-Host "  2. opencode models"
Write-Host "  3. opencode debug config"
Write-Host "  4. opencode"
Write-Host ""
Write-Host "Do not use 'opencode agent list' with your installed CLI."
Write-Host ""