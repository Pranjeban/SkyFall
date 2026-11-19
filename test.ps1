
#requires -Version 5.1
<#
.SYNOPSIS
    Safely switches all SKYFALL OpenCode agents to another available model.

.DESCRIPTION
    - Discovers models using the installed OpenCode CLI.
    - Allows interactive model selection.
    - Backs up all agent definitions before modification.
    - Updates model frontmatter without changing agent instructions.
    - Validates every modified agent.
    - Supports rollback.

.EXAMPLE
    .\Update-SkyfallAgentModels.ps1

.EXAMPLE
    .\Update-SkyfallAgentModels.ps1 -ModelId "opencode/model-id"

.EXAMPLE
    .\Update-SkyfallAgentModels.ps1 -Rollback
#>

[CmdletBinding()]
param(
    [string]$ProjectRoot = $PSScriptRoot,

    [string]$ModelId,

    [switch]$Rollback
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$AgentDirectory = Join-Path $ProjectRoot ".opencode\agents"
$BackupRoot = Join-Path $ProjectRoot ".opencode\backups"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-WarningMessage {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Failure {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Get-AgentFiles {
    if (-not (Test-Path -LiteralPath $AgentDirectory)) {
        throw "Agent directory not found: $AgentDirectory"
    }

    $files = @(
        Get-ChildItem -LiteralPath $AgentDirectory -File -Filter "*.md" |
        Sort-Object Name
    )

    if ($files.Count -eq 0) {
        throw "No agent Markdown files were found."
    }

    return $files
}

function Get-AvailableModels {
    Write-Info "Discovering models through OpenCode CLI..."

    $command = Get-Command opencode -ErrorAction SilentlyContinue

    if (-not $command) {
        throw "OpenCode CLI was not found in PATH."
    }

    $output = @(& opencode models 2>&1)

    if ($LASTEXITCODE -ne 0) {
        throw "The command 'opencode models' failed. Check your OpenCode installation."
    }

    $rawOutput = ($output | ForEach-Object { "$_" }) -join "`n"

    # Extract provider/model identifiers from the actual CLI output.
    $matches = [regex]::Matches(
        $rawOutput,
        '(?<![\w.-])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:#[A-Za-z0-9_.-]+)?)(?![\w.-])'
    )

    $models = @(
        $matches |
        ForEach-Object { $_.Groups[1].Value } |
        Sort-Object -Unique
    )

    return $models
}

function Select-Model {
    param(
        [string[]]$Models
    )

    if ($Models.Count -eq 0) {
        Write-WarningMessage "No provider/model identifiers could be extracted."
        Write-Host ""
        Write-Host "Run 'opencode models' and enter an exact model ID."
        return (Read-Host "Model ID")
    }

    Write-Host ""
    Write-Host "============================================" -ForegroundColor Magenta
    Write-Host " AVAILABLE OPENCODE MODELS" -ForegroundColor Magenta
    Write-Host "============================================" -ForegroundColor Magenta

    for ($i = 0; $i -lt $Models.Count; $i++) {
        Write-Host ("[{0}] {1}" -f ($i + 1), $Models[$i])
    }

    Write-Host ""
    $selection = Read-Host "Select model number or enter an exact model ID"

    $number = 0

    if ([int]::TryParse($selection, [ref]$number)) {
        if ($number -lt 1 -or $number -gt $Models.Count) {
            throw "Invalid model selection."
        }

        return $Models[$number - 1]
    }

    if ($selection -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:#[A-Za-z0-9_.-]+)?$') {
        throw "Invalid model ID format. Expected provider/model."
    }

    return $selection
}

function Get-Frontmatter {
    param(
        [string]$Content,
        [string]$FileName
    )

    $lines = $Content -split "`r?`n"

    if ($lines.Count -lt 3 -or $lines[0].Trim() -ne "---") {
        throw "Invalid frontmatter opening in $FileName"
    }

    $closingIndex = -1

    for ($i = 1; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq "---") {
            $closingIndex = $i
            break
        }
    }

    if ($closingIndex -lt 0) {
        throw "Frontmatter closing delimiter not found in $FileName"
    }

    return @{
        Lines = $lines
        ClosingIndex = $closingIndex
    }
}

function Update-AgentModel {
    param(
        [string]$Path,
        [string]$NewModel
    )

    $content = [System.IO.File]::ReadAllText($Path)
    $parsed = Get-Frontmatter -Content $content -FileName (Split-Path $Path -Leaf)

    $lines = [System.Collections.Generic.List[string]]::new()

    foreach ($line in $parsed.Lines) {
        $lines.Add($line)
    }

    $modelIndexes = @()

    for ($i = 1; $i -lt $parsed.ClosingIndex; $i++) {
        if ($lines[$i] -match '^\s*model\s*:') {
            $modelIndexes += $i
        }
    }

    if ($modelIndexes.Count -gt 1) {
        throw "Multiple model declarations found in $(Split-Path $Path -Leaf)"
    }

    if ($modelIndexes.Count -eq 1) {
        $lines[$modelIndexes[0]] = "model: $NewModel"
    }
    else {
        # Add model declaration inside frontmatter.
        $lines.Insert($parsed.ClosingIndex, "model: $NewModel")
    }

    $updated = $lines -join "`r`n"

    # Validate updated frontmatter before writing.
    $validation = Get-Frontmatter -Content $updated -FileName (Split-Path $Path -Leaf)

    $modelLine = @(
        $validation.Lines |
        Where-Object { $_ -match '^\s*model\s*:\s*.+$' }
    )

    if ($modelLine.Count -ne 1) {
        throw "Model validation failed for $(Split-Path $Path -Leaf)"
    }

    [System.IO.File]::WriteAllText(
        $Path,
        $updated,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Restore-LatestBackup {
    if (-not (Test-Path -LiteralPath $BackupRoot)) {
        throw "No backup directory exists."
    }

    $backups = @(
        Get-ChildItem -LiteralPath $BackupRoot -Directory |
        Where-Object { $_.Name -like "Model-Switch-*" } |
        Sort-Object Name -Descending
    )

    if ($backups.Count -eq 0) {
        throw "No model-switch backup was found."
    }

    Write-Host ""
    Write-Host "Available backups:" -ForegroundColor Cyan

    for ($i = 0; $i -lt $backups.Count; $i++) {
        Write-Host "[$($i + 1)] $($backups[$i].Name)"
    }

    $choice = Read-Host "Select backup to restore (Enter for latest)"

    $selected = $backups[0]

    if (-not [string]::IsNullOrWhiteSpace($choice)) {
        $number = 0

        if (-not [int]::TryParse($choice, [ref]$number) -or
            $number -lt 1 -or $number -gt $backups.Count) {
            throw "Invalid backup selection."
        }

        $selected = $backups[$number - 1]
    }

    $confirm = Read-Host "Restore $($selected.Name)? Type YES"

    if ($confirm -cne "YES") {
        Write-WarningMessage "Rollback cancelled."
        return
    }

    $restored = 0

    Get-ChildItem -LiteralPath $selected.FullName -File -Filter "*.md" |
    ForEach-Object {
        $destination = Join-Path $AgentDirectory $_.Name

        Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
        $restored++
    }

    Write-Success "Restored $restored agent definitions."
}

try {
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host " SKYFALL - AGENT MODEL MANAGEMENT" -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan

    if (-not (Test-Path -LiteralPath $ProjectRoot)) {
        throw "Project root does not exist: $ProjectRoot"
    }

    if ($Rollback) {
        Restore-LatestBackup
        exit 0
    }

    $agents = @(Get-AgentFiles)

    Write-Info "Project: $ProjectRoot"
    Write-Info "Found $($agents.Count) agent definitions."

    if ([string]::IsNullOrWhiteSpace($ModelId)) {
        $availableModels = @(Get-AvailableModels)
        $ModelId = Select-Model -Models $availableModels
    }

    if ($ModelId -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:#[A-Za-z0-9_.-]+)?$') {
        throw "Invalid model ID: $ModelId"
    }

    Write-Host ""
    Write-Host "Selected model: $ModelId" -ForegroundColor Yellow
    Write-Host ""

    foreach ($agent in $agents) {
        Write-Host ("  - {0}" -f $agent.Name)
    }

    Write-Host ""
    $confirmation = Read-Host "Apply this model to all listed agents? Type YES"

    if ($confirmation -cne "YES") {
        Write-WarningMessage "No agent files were changed."
        exit 0
    }

    # Back up the complete agent directory contents before modifications.
    $backupDirectory = Join-Path $BackupRoot "Model-Switch-$Timestamp"

    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null

    foreach ($agent in $agents) {
        Copy-Item -LiteralPath $agent.FullName -Destination $backupDirectory
    }

    Write-Success "Agent backup created: $backupDirectory"

    $updated = 0

    foreach ($agent in $agents) {
        Write-Info "Updating $($agent.Name)..."

        Update-AgentModel -Path $agent.FullName -NewModel $ModelId

        $updated++
        Write-Success "$($agent.Name) updated."
    }

    # Final verification.
    $failures = @()

    foreach ($agent in $agents) {
        $content = [System.IO.File]::ReadAllText($agent.FullName)
        $parsed = Get-Frontmatter -Content $content -FileName $agent.Name

        $modelLines = @(
            $parsed.Lines |
            Where-Object { $_ -match '^\s*model\s*:\s*(.+?)\s*$' }
        )

        if ($modelLines.Count -ne 1 -or
            $modelLines[0] -notmatch [regex]::Escape($ModelId) + '$') {
            $failures += $agent.Name
        }
    }

    if ($failures.Count -gt 0) {
        Write-Failure "Validation failed. Affected agents: $($failures -join ', ')"
        Write-WarningMessage "Original files are preserved in $backupDirectory"
        throw "Final validation failed."
    }

    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host " MODEL UPDATE COMPLETED" -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green

    Write-Success "Updated agents: $updated"
    Write-Success "Selected model: $ModelId"
    Write-Success "Backup: $backupDirectory"

    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Start a new OpenCode session."
    Write-Host "2. Verify the selected model with /models."
    Write-Host "3. Test the Orchestrator and one specialist agent."
    Write-Host ""
    Write-Host "Rollback command:" -ForegroundColor Yellow
    Write-Host ".\Update-SkyfallAgentModels.ps1 -Rollback"

}
catch {
    Write-Failure $_.Exception.Message
    exit 1
}
