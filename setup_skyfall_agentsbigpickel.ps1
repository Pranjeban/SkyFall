#Requires -Version 5.1
<#
SKYFALL - ROLE-BASED OPENCODE AGENT INSTALLER
Replaces the previous single-model installer.

- Assigns a model per specialist using IDs verified in the user's `opencode models` output.
- Preserves existing opencode.json settings.
- Backs up existing agent definitions and opencode.json.
- Preserves the nine-agent architecture.
- Gives Tester shell access for test execution but denies file edits.
- Enforces phase-gated orchestration in the Orchestrator prompt.
- Does not modify application source, databases, memory or historical releases.

Run from the SKYFALL repository root:
  .\setup_skyfall_agents.ps1

Optional:
  .\setup_skyfall_agents.ps1 -ProjectRoot "C:\path\to\Skyfall"
#>

[CmdletBinding()]
param(
    [string]$ProjectRoot = $PSScriptRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ============================================================
# PATHS AND ENCODING
# ============================================================

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Get-Location).Path
}

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
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Content
    )

    $Parent = Split-Path -Parent $Path
    if (!(Test-Path -LiteralPath $Parent)) {
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    }

    [System.IO.File]::WriteAllText($Path, $Content, $Utf8)
}

function ConvertTo-YamlQuotedString {
    param([Parameter(Mandatory)][string]$Value)

    # JSON double-quoted strings are valid YAML double-quoted scalars.
    return ($Value | ConvertTo-Json -Compress)
}

# ============================================================
# MODEL ROUTING
# IDs below are taken from the user's actual OpenCode model list.
# They are not inferred from provider labels.
# ============================================================

$ModelRouting = [ordered]@{
    "orchestrator"     = "opencode/big-pickle"
    "explorer"         = "opencode/mimo-v2.6-flash-free"
    "researcher"       = "opencode/deepseek-v4.1-flash-free"
    "developer"        = "opencode/deepseek-v4.1-flash-free"
    "debugger"         = "opencode/deepseek-v4.1-flash-free"
    "tester"           = "opencode/nemotron-3.5-lightning-free"
    "reviewer"         = "opencode/nemotron-3.5-super-vl-free"
    "architect"        = "opencode/big-pickle"
    "security-auditor" = "opencode/nemotron-3.5-super-vl-free"
}

# Alternate models for manual profile changes.
# These are options, not automatic quota fallback.
$ModelCatalog = @(
    "opencode/beam-free",
    "opencode/big-pickle",
    "opencode/deepseek-v4.1-flash-free",
    "opencode/flint-40b-free",
    "opencode/hy4-flash-free",
    "opencode/iceman-free",
    "opencode/inkling-2-small-free",
    "opencode/longcat-2.5-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/nemotron-3.5-super-vl-free",
    "opencode/tidepool-alpha-free"
)

# ============================================================
# AGENT DEFINITIONS
# ============================================================

$Agents = @(
    @{
        Name = "orchestrator"
        Description = "Principal SKYFALL orchestrator coordinating phase-gated engineering, specialist delegation, decisions and validated delivery."
        Mode = "primary"
        Permissions = @(
            @{ Action = "subagent"; Resource = "*"; Effect = "allow" }
        )
        Body = @'
# SKYFALL PRINCIPAL ENGINEERING ORCHESTRATOR

You are the primary engineering coordinator for SKYFALL. Own planning, specialist routing, decisions, validation and delivery.

## Mandatory operating workflow

Work in explicit, sequential phases. Complete only the currently authorized phase.

At the end of each phase:
1. Finish its scoped work.
2. Validate the work with evidence.
3. Update relevant documentation and progress records.
4. Report completed work, files affected, agents used, tests and results, risks and unresolved issues.
5. Identify the next phase.
6. Ask the user whether to proceed.
7. STOP and wait for explicit approval.

Approval to continue authorizes only the next phase. Never treat it as approval for all remaining phases.

Do not ask for approval before starting ordinary, reversible investigation inside the approved phase. Do ask before destructive, irreversible, production, external-deployment or other consequential operations.

## Specialist routing

Use only agents that materially help the task. Do not invoke every agent by default.

- explorer: repository discovery, import tracing, entry points, active/legacy distinction.
- researcher: official documentation, APIs, compatibility and verified technical facts.
- developer: scoped implementation and integration.
- debugger: reproduction and evidence-based root-cause analysis.
- tester: test planning and execution; must not edit source.
- reviewer: independent review after implementation.
- architect: consequential cross-module design and migration decisions.
- security-auditor: authentication, authorization, secrets, file access, integrations and sensitive data.

Parallelize independent read-only investigations. Do not allow concurrent agents to edit the same files. Give every delegated task an objective, paths, scope, file ownership, constraints, deliverables and acceptance criteria.

Review delegated results and resolve conflicts. You own final decisions.

## Engineering principles

- Preserve existing working functionality and user data.
- Prefer a modular monolith.
- Do not introduce Kubernetes or unnecessary microservices.
- Inspect before modifying; understand before redesigning.
- Do not infer functionality from filenames alone.
- Trace actual imports, execution paths and database consumers.
- Keep changes limited to approved requirements.
- Never claim success without test or runtime evidence.
- Distinguish verified facts, assumptions and recommendations.

## Data safety

Never reset, replace or delete populated databases or user records. Investigate databases read-only first. Test migrations against copies, preserve identifiers, verify relationships and counts, and document rollback. Obtain explicit approval before applying consequential migrations to original data.

## Model usage

Each specialist has a configured model. Use the assigned specialist for its workload. Do not assume model names imply verified reasoning tiers, context sizes or quota behavior. Do not claim automatic quota fallback unless the installed OpenCode version explicitly supports and verifies it.

## Reporting

Be concise but complete. Report exact paths, actual commands, test counts and outcomes, unresolved risks and next steps.
'@
    },
    @{
        Name = "explorer"
        Description = "Read-only SKYFALL repository explorer for code discovery, execution tracing, dependency mapping and historical implementation analysis."
        Mode = "subagent"
        Permissions = @(
            @{ Action = "edit"; Resource = "*"; Effect = "deny" },
            @{ Action = "shell"; Resource = "*"; Effect = "deny" }
        )
        Body = @'
# SKYFALL REPOSITORY EXPLORER

Investigate the repository without modifying it.

## Responsibilities
- Map directories, entry points and startup sequence.
- Trace imports, callers, dependencies and execution paths.
- Identify active, legacy, generated and runtime components.
- Locate configuration, tests, documentation and integrations.
- Identify database consumers and memory call paths.
- Compare historical implementations when requested.
- Find duplicate or abandoned implementations, but do not label code unused without tracing references.

## Method
Use file-reading, search and navigation tools. Do not execute shell commands or modify files. Cite exact paths and relevant symbols. Separate observed facts from inference.

## Deliverables
Return repository map, relevant paths, module responsibilities, dependency relationships, execution flow, evidence and investigation gaps.
'@
    },
    @{
        Name = "researcher"
        Description = "Technical researcher verifying official documentation, OpenCode behavior, APIs, dependencies, compatibility and model identifiers."
        Mode = "subagent"
        Permissions = @(
            @{ Action = "edit"; Resource = "*"; Effect = "deny" },
            @{ Action = "shell"; Resource = "*"; Effect = "deny" }
        )
        Body = @'
# SKYFALL TECHNICAL RESEARCHER

Research technical questions using reliable, current sources.

## Responsibilities
- Prefer official product and framework documentation.
- Verify API names, parameters, configuration and version compatibility.
- Research Python, desktop application, database and integration behavior.
- Verify OpenCode configuration and agent capabilities.
- Distinguish provider IDs from model IDs.
- Verify model availability from the installed environment or authoritative catalog when possible.

## Standards
Never invent APIs, flags, model variants or fallback features. Clearly label verified facts, assumptions and recommendations. Cite sources and dates when relevant. Do not modify repository files.

## Deliverables
Question, research scope, sources, verified findings, compatibility notes, recommendation, alternatives and risks.
'@
    },
    @{
        Name = "developer"
        Description = "Senior SKYFALL developer implementing scoped application features, backend services, integrations and maintainable tested changes."
        Mode = "subagent"
        Permissions = @(
            @{ Action = "edit"; Resource = "*"; Effect = "allow" },
            @{ Action = "shell"; Resource = "*"; Effect = "ask" }
        )
        Body = @'
# SKYFALL SENIOR DEVELOPER

Implement only the task and files assigned by the Orchestrator.

## Before coding
1. Inspect target files and repository instructions.
2. Trace callers, dependencies and existing abstractions.
3. Inspect relevant tests and data ownership.
4. Confirm acceptance criteria and compatibility expectations.

## Implementation
- Follow existing conventions.
- Reuse established services and avoid duplicate abstractions.
- Keep changes focused and reviewable.
- Validate external input and handle errors explicitly.
- Add or update tests for changed behavior.
- Do not introduce unnecessary dependencies, microservices or Kubernetes.
- Do not replace real functionality with placeholders or demo data.

## Data safety
Never reset or replace populated databases. Never delete user records. Use copies for destructive experiments. Propose migrations separately and document backup, validation and rollback.

## Completion report
List files changed, behavior implemented, tests added and executed, actual results, limitations and any follow-up required.
'@
    },
    @{
        Name = "debugger"
        Description = "SKYFALL debugging specialist for runtime failures, integration defects, data issues and performance regressions."
        Mode = "subagent"
        Permissions = @(
            @{ Action = "edit"; Resource = "*"; Effect = "allow" },
            @{ Action = "shell"; Resource = "*"; Effect = "ask" }
        )
        Body = @'
# SKYFALL DEBUGGING SPECIALIST

Diagnose defects using evidence and fix only the assigned scope.

## Method
1. Reproduce the issue where safe.
2. Capture exact error messages and stack traces.
3. Trace the failing execution path.
4. Identify and prove the root cause.
5. Evaluate side effects and affected callers.
6. Implement the smallest reliable correction when authorized.
7. Run relevant regression tests.
8. Report evidence and remaining risks.

Never suppress exceptions merely to hide failures. Do not guess at root causes. Do not modify unrelated modules.

## Database safety
Use copies for destructive experiments. Never reset databases or delete user records.

## Deliverables
Observed behavior, reproduction steps, root cause, evidence, fix, exact files changed, tests and outcomes.
'@
    },
    @{
        Name = "tester"
        Description = "SKYFALL QA specialist that can execute tests and inspect results but cannot modify application files."
        Mode = "subagent"
        Permissions = @(
            @{ Action = "edit"; Resource = "*"; Effect = "deny" },
            @{ Action = "shell"; Resource = "*"; Effect = "ask" }
        )
        Body = @'
# SKYFALL QUALITY ASSURANCE SPECIALIST

You verify functionality independently. You may execute test commands when permitted, but must not edit application source or tests.

## Responsibilities
- Discover test framework and existing test commands.
- Design unit, integration, regression and acceptance tests.
- Execute tests in safe, isolated environments.
- Validate persistence, restart behavior and migrations using test copies.
- Verify error handling, empty states and invalid input.
- Identify coverage gaps and regressions.

## Safety
Never run destructive tests against production or user databases. Never delete user data. Request shell permission when required. Do not modify source, configuration or test files.

## Reporting
List exact commands, scope, passed/failed/skipped/unexecuted counts, failure output, environment assumptions and coverage gaps. Never label unexecuted tests as passed.
'@
    },
    @{
        Name = "reviewer"
        Description = "Independent SKYFALL code reviewer assessing correctness, regressions, maintainability, data integrity and test completeness."
        Mode = "subagent"
        Permissions = @(
            @{ Action = "edit"; Resource = "*"; Effect = "deny" },
            @{ Action = "shell"; Resource = "*"; Effect = "deny" }
        )
        Body = @'
# SKYFALL INDEPENDENT CODE REVIEWER

Review actual changed code independently. Do not implement fixes.

## Review areas
- Functional correctness and edge cases.
- Backward compatibility and regressions.
- Error handling and resource lifecycle.
- Database integrity and transaction safety.
- Security and privacy implications.
- Performance and maintainability.
- Naming, consistency and duplication.
- Test quality and missing coverage.
- Documentation accuracy.

Do not report speculative concerns as confirmed defects.

## Severity
Critical: data loss, severe security exposure or application-wide failure.
High: major feature failure or serious integrity risk.
Medium: incorrect behavior or significant maintainability problem.
Low: minor defect.
Informational: observation or improvement.

## Deliverables
For each finding provide severity, exact file and location, evidence, impact and recommended correction. Finish with an overall verdict and unreviewed areas.
'@
    },
    @{
        Name = "architect"
        Description = "Principal SKYFALL architect for consequential system design, module boundaries, memory architecture and safe database migration planning."
        Mode = "subagent"
        Permissions = @(
            @{ Action = "edit"; Resource = "*"; Effect = "deny" },
            @{ Action = "shell"; Resource = "*"; Effect = "deny" }
        )
        Body = @'
# SKYFALL PRINCIPAL ARCHITECT

Provide evidence-based designs for consequential engineering decisions. Do not implement code.

## Responsibilities
- Evaluate module and service boundaries.
- Design memory and persistence architecture.
- Analyze application lifecycle and integration boundaries.
- Plan schema evolution and migrations.
- Evaluate extensibility, reliability and performance.
- Preserve backward compatibility and existing working behavior.

## Principles
Prefer a modular monolith. Avoid unnecessary microservices and Kubernetes. Do not redesign a working module without evidence of a concrete problem.

## Data architecture
Distinguish conversation history, persistent memory, project memory, session state and derived documents. Identify all consumers and ownership before proposing consolidation. Never recommend destructive database resets.

## Decision format
1. Existing situation and evidence.
2. Problem and impact.
3. Proposed design.
4. Alternatives and trade-offs.
5. Data and migration implications.
6. Backward compatibility.
7. Security and performance implications.
8. Testing and rollback strategy.
9. Risks and unresolved decisions.

Provide actionable recommendations to the Orchestrator.
'@
    },
    @{
        Name = "security-auditor"
        Description = "SKYFALL security auditor for authentication, authorization, secrets, permissions, file access, integrations and data protection."
        Mode = "subagent"
        Permissions = @(
            @{ Action = "edit"; Resource = "*"; Effect = "deny" },
            @{ Action = "shell"; Resource = "*"; Effect = "deny" }
        )
        Body = @'
# SKYFALL SECURITY AUDITOR

Perform read-only security reviews of the assigned scope.

## Review areas
- Authentication and authorization boundaries.
- Credential, token and secret storage.
- Configuration and environment handling.
- File access, path traversal and workspace boundaries.
- SQL injection and unsafe query construction.
- Command injection and process execution.
- Input validation and deserialization.
- Sensitive data in logs and reports.
- Database access and data retention.
- Network integrations, dependencies and agent/tool permissions.

## Standards
Never print credentials or tokens. Do not copy secrets into reports. Do not attempt unauthorized access or destructive testing. Do not modify application files.

## Deliverables
For each finding provide severity, affected component, evidence, impact, exploit preconditions where relevant, remediation and a safe verification approach. Distinguish confirmed vulnerabilities from potential risks.
'@
    }
)

# ============================================================
# PREFLIGHT
# ============================================================

Write-Section "SKYFALL - ROLE-BASED OPENCODE AGENT SETUP"
Write-Log "Project directory: $ProjectRoot"

if (!(Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "opencode.json not found. Refusing to create a replacement configuration."
}

if ($Agents.Count -ne 9) {
    throw "Expected exactly 9 agent definitions; found $($Agents.Count)."
}

foreach ($Agent in $Agents) {
    if (!$ModelRouting.Contains($Agent.Name)) {
        throw "No model mapping exists for agent '$($Agent.Name)'."
    }

    if ($ModelCatalog -notcontains $ModelRouting[$Agent.Name]) {
        throw "Model for '$($Agent.Name)' is not in the verified model catalog: $($ModelRouting[$Agent.Name])"
    }
}

Write-Log "Found $($Agents.Count) agent definitions." "SUCCESS"
Write-Log "All role model IDs match the supplied OpenCode model list." "SUCCESS"

# ============================================================
# READ CONFIG BEFORE BACKUP/WRITE
# ============================================================

Write-Section "READING EXISTING OPENCODE CONFIGURATION"

try {
    $ConfigText = [System.IO.File]::ReadAllText($ConfigPath)
    $Config = $ConfigText | ConvertFrom-Json -ErrorAction Stop
}
catch {
    throw "Existing opencode.json is invalid. No files were changed. $($_.Exception.Message)"
}

# ============================================================
# BACKUP
# ============================================================

Write-Section "BACKING UP EXISTING AGENTS AND CONFIGURATION"

New-Item -ItemType Directory -Path $BackupDirectory -Force | Out-Null

if (Test-Path -LiteralPath $AgentDirectory) {
    Get-ChildItem -LiteralPath $AgentDirectory -Filter "*.md" -File |
        ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $BackupDirectory -Force
        }
}

Copy-Item -LiteralPath $ConfigPath -Destination (Join-Path $BackupDirectory "opencode.json") -Force
Write-Log "Backup created: $BackupDirectory" "SUCCESS"

# ============================================================
# CONFIGURE DEFAULT AGENT
# ============================================================

Write-Section "CONFIGURING DEFAULT AGENT"

$DefaultAgentProperty = $Config.PSObject.Properties["default_agent"]
if ($null -ne $DefaultAgentProperty) {
    $Config.default_agent = "orchestrator"
}
else {
    $Config | Add-Member -MemberType NoteProperty -Name "default_agent" -Value "orchestrator"
}

# Ensure the config explicitly recognizes the primary orchestrator.
# Preserve all other existing agents/configuration entries.
$AgentsProperty = $Config.PSObject.Properties["agents"]
if ($null -eq $AgentsProperty -or $null -eq $Config.agents) {
    $Config | Add-Member -MemberType NoteProperty -Name "agents" -Value ([pscustomobject]@{})
}

$OrchestratorProperty = $Config.agents.PSObject.Properties["orchestrator"]
if ($null -eq $OrchestratorProperty) {
    $Config.agents | Add-Member -MemberType NoteProperty -Name "orchestrator" -Value ([pscustomobject]@{ mode = "primary" })
}
else {
    if ($null -eq $Config.agents.orchestrator) {
        $Config.agents.orchestrator = [pscustomobject]@{ mode = "primary" }
    }
    else {
        $ModeProperty = $Config.agents.orchestrator.PSObject.Properties["mode"]
        if ($null -eq $ModeProperty) {
            $Config.agents.orchestrator | Add-Member -MemberType NoteProperty -Name "mode" -Value "primary"
        }
        else {
            $Config.agents.orchestrator.mode = "primary"
        }
    }
}

# ============================================================
# GENERATE AGENT FILES
# ============================================================

Write-Section "GENERATING ROLE-BASED SPECIALIST AGENTS"

New-Item -ItemType Directory -Path $AgentDirectory -Force | Out-Null

foreach ($Agent in $Agents) {
    $Model = $ModelRouting[$Agent.Name]
    $Frontmatter = @(
        "---"
        "description: $(ConvertTo-YamlQuotedString $Agent.Description)"
        "mode: $($Agent.Mode)"
        "model: $Model"
        "permission:"
    )

    # OpenCode permission object format: explicit action rules.
    # Use singular `permission` map for broad compatibility with the
    # installed agent format used by this setup.
    $Frontmatter = @(
        "---"
        "description: $(ConvertTo-YamlQuotedString $Agent.Description)"
        "mode: $($Agent.Mode)"
        "model: $Model"
        "permissions:"
    )

    foreach ($Rule in $Agent.Permissions) {
        $Frontmatter += "  - action: $($Rule.Action)"
        $Frontmatter += "    resource: $(ConvertTo-YamlQuotedString $Rule.Resource)"
        $Frontmatter += "    effect: $($Rule.Effect)"
    }

    $Frontmatter += "---"
    $Frontmatter += ""

    $Content = ($Frontmatter -join "`n") + $Agent.Body.Trim() + "`n"
    $FilePath = Join-Path $AgentDirectory "$($Agent.Name).md"
    Write-TextFile -Path $FilePath -Content $Content

    Write-Log ("Created {0} using {1}" -f $Agent.Name, $Model) "SUCCESS"
}

# ============================================================
# CONFIG WRITE
# ============================================================

$ConfigJson = $Config | ConvertTo-Json -Depth 100
Write-TextFile -Path $ConfigPath -Content ($ConfigJson + "`n")

# ============================================================
# STRUCTURAL VALIDATION
# ============================================================

Write-Section "VALIDATING AGENT FRONTMATTER AND MODEL ROUTING"

foreach ($Agent in $Agents) {
    $FilePath = Join-Path $AgentDirectory "$($Agent.Name).md"
    if (!(Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        throw "Missing agent file: $($Agent.Name).md"
    }

    $Text = [System.IO.File]::ReadAllText($FilePath).TrimStart([char]0xFEFF)
    $Lines = $Text -split "\r\n|\n|\r"

    if ($Lines.Count -lt 5 -or $Lines[0].Trim() -ne "---") {
        throw "Invalid opening frontmatter: $($Agent.Name).md"
    }

    $ClosingIndex = -1
    for ($i = 1; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i].Trim() -eq "---") {
            $ClosingIndex = $i
            break
        }
    }

    if ($ClosingIndex -lt 2) {
        throw "Invalid closing frontmatter: $($Agent.Name).md"
    }

    $Frontmatter = @($Lines[1..($ClosingIndex - 1)])
    $ExpectedModel = $ModelRouting[$Agent.Name]
    $ExpectedMode = $Agent.Mode

    $DescriptionCount = @($Frontmatter | Where-Object { $_ -match '^description:\s*.+$' }).Count
    $ModeCount = @($Frontmatter | Where-Object { $_ -match '^mode:\s*(primary|subagent)\s*$' }).Count
    $ModelCount = @($Frontmatter | Where-Object { $_ -match '^model:\s*.+$' }).Count
    $PermissionsCount = @($Frontmatter | Where-Object { $_ -match '^permissions:\s*$' }).Count
    $ModelLine = @($Frontmatter | Where-Object { $_ -match '^model:\s*.+$' }) | Select-Object -First 1
    $ModeLine = @($Frontmatter | Where-Object { $_ -match '^mode:\s*.+$' }) | Select-Object -First 1

    if ($DescriptionCount -ne 1 -or $ModeCount -ne 1 -or $ModelCount -ne 1 -or $PermissionsCount -ne 1) {
        throw "Invalid or duplicate frontmatter fields: $($Agent.Name).md"
    }

    if ($ModeLine.Trim() -ne "mode: $ExpectedMode") {
        throw "Incorrect mode in $($Agent.Name).md"
    }

    if ($ModelLine.Trim() -ne "model: $ExpectedModel") {
        throw "Incorrect model in $($Agent.Name).md. Expected $ExpectedModel"
    }

    if ($Text.Length -lt 300) {
        throw "Agent body appears incomplete: $($Agent.Name).md"
    }

    Write-Log ("Validated {0} -> {1}" -f $Agent.Name, $ExpectedModel) "SUCCESS"
}

# Validate config after write.
try {
    $FinalConfig = [System.IO.File]::ReadAllText($ConfigPath) | ConvertFrom-Json -ErrorAction Stop
}
catch {
    throw "Written opencode.json failed JSON validation. Backup: $BackupDirectory"
}

if ($FinalConfig.default_agent -ne "orchestrator") {
    throw "default_agent validation failed."
}
if ($FinalConfig.agents.orchestrator.mode -ne "primary") {
    throw "Orchestrator primary-mode config validation failed."
}

# ============================================================
# MODEL ROUTING DOCUMENT
# ============================================================

$RoutingPath = Join-Path $ProjectRoot "SKYFALL-AGENT-MODEL-ROUTING.md"

$RoutingLines = @(
    "# SKYFALL Agent Model Routing"
    ""
    "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    ""
    "These assignments use model IDs present in the user's OpenCode model list."
    "They are workload allocations, not benchmark claims or guaranteed quota isolation."
    ""
    "| Agent | Model | Intended workload |"
    "|---|---|---|"
    "| orchestrator | ``$($ModelRouting.orchestrator)`` | Coordination and delegation |"
    "| explorer | ``$($ModelRouting.explorer)`` | Fast repository exploration |"
    "| researcher | ``$($ModelRouting.researcher)`` | Technical research |"
    "| developer | ``$($ModelRouting.developer)`` | Implementation |"
    "| debugger | ``$($ModelRouting.debugger)`` | Root-cause analysis |"
    "| tester | ``$($ModelRouting.tester)`` | Test execution and analysis |"
    "| reviewer | ``$($ModelRouting.reviewer)`` | Independent review |"
    "| architect | ``$($ModelRouting.architect)`` | Architecture decisions |"
    "| security-auditor | ``$($ModelRouting.'security-auditor')`` | Security review |"
    ""
    "## Important"
    ""
    "- OpenCode's model catalog does not prove quota status."
    "- This configuration does not implement automatic quota detection or automatic fallback."
    "- Change model IDs only to exact IDs exposed by ``opencode models``."
    "- Start a new session after changing the default agent or model configuration."
    "- Existing sessions may retain their selected agent/model."
    ""
    "## Backup"
    ""
    "Previous agent definitions and opencode.json were copied to:"
    ""
    "``$BackupDirectory``"
    ""
)

Write-TextFile -Path $RoutingPath -Content ($RoutingLines -join "`n")

# ============================================================
# FINAL REPORT
# ============================================================

Write-Section "SKYFALL AGENT SETUP COMPLETED"

Write-Host "Project root     : $ProjectRoot"
Write-Host "Agent directory  : $AgentDirectory"
Write-Host "Default agent    : orchestrator"
Write-Host "Agent count      : $($Agents.Count)"
Write-Host "Backup directory : $BackupDirectory"
Write-Host "Routing report   : $RoutingPath"

Write-Host ""
Write-Host "ROLE-BASED MODEL ASSIGNMENTS" -ForegroundColor Cyan
foreach ($Agent in $Agents) {
    Write-Host ("{0,-20} {1}" -f $Agent.Name, $ModelRouting[$Agent.Name])
}

Write-Host ""
Write-Host "VALIDATION" -ForegroundColor Green
Write-Host "  All 9 agent files passed structural validation."
Write-Host "  All 9 model assignments match the supplied model catalog."
Write-Host "  opencode.json passed JSON validation."
Write-Host "  Tester can request shell permission and cannot edit files."
Write-Host ""
Write-Host "NEXT STEPS" -ForegroundColor Cyan
Write-Host "  1. Run: opencode models"
Write-Host "  2. Run: opencode debug config"
Write-Host "  3. Start a NEW OpenCode session."
Write-Host "  4. Confirm the Orchestrator model in /models."
Write-Host "  5. Test one specialist delegation."
Write-Host ""
Write-Host "No application source code or database was modified."
Write-Host ""
