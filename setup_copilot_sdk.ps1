# ============================================================
# SKYFALL - Copilot SDK setup and connection smoke test prep
# Install into the virtual environment beside this script.
# Does not modify SKYFALL desktop source files.
# ============================================================

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Requirements = Join-Path $Root 'requirements.txt'
$TestScript = Join-Path $Root 'test_copilot_connection.py'
$PackageSpec = 'github-copilot-sdk==1.0.34'

Write-Host ''
Write-Host '==============================================' -ForegroundColor Cyan
Write-Host ' SKYFALL - COPILOT SDK SETUP' -ForegroundColor Cyan
Write-Host '==============================================' -ForegroundColor Cyan
Write-Host "Project root: $Root"

if (-not (Test-Path $Python)) {
    throw "SKYFALL virtual environment was not found: $Python. Run setup_skyfall.ps1 first."
}

if (-not (Test-Path $Requirements)) {
    throw "requirements.txt was not found: $Requirements"
}

# Add a pinned, known GA-era SDK version without replacing the user's file.
$RequirementLines = @(Get-Content $Requirements)
$ExistingSdkLines = @($RequirementLines | Where-Object { $_ -match '^\s*(github-copilot-sdk|microsoft-copilot-sdk)(\s|[<=>!~;\[])' })

if ($ExistingSdkLines.Count -eq 0) {
    Add-Content -Path $Requirements -Value "`r`n# GitHub Copilot SDK (pinned for repeatable integration)`r`n$PackageSpec" -Encoding UTF8
    Write-Host '[1/4] Added pinned Copilot SDK dependency to requirements.txt.' -ForegroundColor Green
}
elseif ($ExistingSdkLines -contains $PackageSpec) {
    Write-Host '[1/4] Pinned Copilot SDK dependency is already present.' -ForegroundColor Green
}
else {
    Write-Host '[1/4] An existing Copilot SDK requirement was found:' -ForegroundColor Yellow
    $ExistingSdkLines | ForEach-Object { Write-Host "  $_" }
    throw 'Resolve the existing SDK requirement manually before installing; setup stopped to avoid conflicting package versions.'
}

# Install with Windows trust-store integration, preserving TLS verification.
Write-Host "`n[2/4] Installing $PackageSpec ..." -ForegroundColor Cyan
& $Python -m pip install --use-feature=truststore $PackageSpec
if ($LASTEXITCODE -ne 0) {
    throw 'Copilot SDK installation failed. Do not disable TLS verification; share the sanitized error output.'
}

# Verify the SDK can be imported.
Write-Host "`n[3/4] Verifying Python SDK import..." -ForegroundColor Cyan
& $Python -c 'from copilot import CopilotClient; print("Copilot SDK import successful")'
if ($LASTEXITCODE -ne 0) {
    throw 'The package installed but the expected Python import failed.'
}

# Pre-download the matching SDK runtime. The SDK verifies the published checksum.
Write-Host "`n[4/4] Downloading the SDK-matched Copilot runtime..." -ForegroundColor Cyan
& $Python -m copilot download-runtime
if ($LASTEXITCODE -ne 0) {
    throw 'Runtime download failed. The SDK package is installed, but the runtime is not ready. Share the sanitized error output.'
}

Write-Host ''
Write-Host '==============================================' -ForegroundColor Green
Write-Host ' COPILOT SDK SETUP COMPLETE' -ForegroundColor Green
Write-Host '==============================================' -ForegroundColor Green
Write-Host 'Next: run .\.venv\Scripts\python.exe .\test_copilot_connection.py'
Write-Host 'This smoke test uses an empty tool mode and registers no tools.'
