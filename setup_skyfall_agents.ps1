
#Requires -Version 5.1

<#
SKYFALL - OPENCODE SPECIALIST AGENT INSTALLER

Creates:
  orchestrator
  explorer
  researcher
  developer
  debugger
  tester
  reviewer
  architect
  security-auditor

Preserves:
  Existing opencode.json settings
  Existing agent files through timestamped backups

Does not modify:
  Application source code
  SQLite databases
  Historical releases
  Existing project memory
#>

[CmdletBinding()]
param(
    [string]$ProjectRoot = $PSScriptRoot,
    [string]$Model = "opencode/beam-free"
)

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
        Name = "orchestrator"
        Description = "Primary SKYFALL engineering orchestrator coordinating specialist agents, architecture, implementation and delivery."
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

## Specialist agents

Use the following agents when appropriate:

- explorer: repository exploration.
- researcher: technical research.
- developer: implementation.
- debugger: root-cause analysis.
- tester: quality assurance.
- reviewer: independent code review.
- architect: architecture and migration decisions.
- security-auditor: security assessment.

## Delegation

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
# PREFLIGHT
# ============================================================

Write-Section "SKYFALL - OPENCODE AGENT SETUP"

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

Write-Log "Existing configuration backed up." "SUCCESS"
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
# CONFIGURE DEFAULT AGENT
# ============================================================

Write-Section "CONFIGURING DEFAULT AGENT"

$DefaultAgentProperty = $Config.PSObject.Properties["default_agent"]

if ($null -ne $DefaultAgentProperty) {
    $Config.default_agent = "orchestrator"
}
else {
    $Config | Add-Member -MemberType NoteProperty `
        -Name "default_agent" `
        -Value "orchestrator"
}

$ConfigJson = $Config | ConvertTo-Json -Depth 100

Write-TextFile -Path $ConfigPath -Content ($ConfigJson + "`n")

Write-Log "Default agent set to orchestrator." "SUCCESS"
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
        "model: $Model"
        "permissions:"
    )

    if ($Name -eq "orchestrator") {

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

    if (!$PermissionsLine) {
        throw "Missing permissions declaration: $Name.md"
    }

    $ExpectedMode = if ($Name -eq "orchestrator") {
        "primary"
    }
    else {
        "subagent"
    }

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

Write-Log "JSON configuration is valid." "SUCCESS"
Write-Log "Default agent verified." "SUCCESS"

# ============================================================
# ROUTING DOCUMENTATION
# ============================================================

Write-Section "CREATING MODEL ROUTING DOCUMENTATION"

$RoutingDocumentation = Join-Path $ProjectRoot "DYNAMIC-MODEL-ROUTING.md"

$RoutingText = @'
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
'@

Write-TextFile -Path $RoutingDocumentation -Content $RoutingText

Write-Log "Routing documentation created." "SUCCESS"

# ============================================================
# FINAL REPORT
# ============================================================

Write-Section "SETUP COMPLETED"

Write-Host "Project root      : $ProjectRoot"
Write-Host "Agent directory   : $AgentDirectory"
Write-Host "Default agent     : orchestrator"
Write-Host "Model             : $Model"
Write-Host "Agent count       : $($Agents.Count)"
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
Write-Host "  1. opencode models"
Write-Host "  2. opencode debug config"
Write-Host "  3. opencode"
Write-Host ""
Write-Host "Do not use 'opencode agent list' with your installed CLI."
Write-Host ""
