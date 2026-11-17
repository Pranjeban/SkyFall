
# ============================================================
# SKYFALL - Local Application Foundation
# Windows 11 | Python 3.11 | PowerShell 7
# ============================================================

$ErrorActionPreference = "Stop"

$Root = Join-Path $env:USERPROFILE "Skyfall"

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "        SKYFALL APPLICATION SETUP"
Write-Host "==============================================" -ForegroundColor Cyan

# ------------------------------------------------------------
# 1. Validate application directory
# ------------------------------------------------------------

if (-not (Test-Path $Root)) {
    New-Item -ItemType Directory -Path $Root -Force |
        Out-Null
}

Set-Location $Root

Write-Host "`n[1/5] Application directory verified." -ForegroundColor Green
Write-Host $Root

# ------------------------------------------------------------
# 2. Create architecture directories
# ------------------------------------------------------------

$Directories = @(
    "app",
    "app\desktop",
    "app\floating",
    "app\components",

    "backend",
    "backend\core",
    "backend\intelligence",
    "backend\orchestrator",
    "backend\services",

    "integrations",
    "integrations\copilot",
    "integrations\azure",
    "integrations\power_platform",

    "mcp",
    "mcp\servers",
    "mcp\tools",
    "mcp\resources",

    "execution",
    "execution\powershell",
    "execution\python",

    "memory",
    "configuration",
    "database",

    "logs",

    "reports",
    "reports\Azure",
    "reports\PowerPlatform",
    "reports\Dynamics365",
    "reports\General",

    "scripts",
    "scripts\generated",
    "scripts\reusable",

    "assets",
    "assets\icons",
    "assets\audio",

    "tests",
    "tests\unit",
    "tests\integration",
    "tests\security"
)

foreach ($Directory in $Directories) {
    $Path = Join-Path $Root $Directory

    New-Item -ItemType Directory -Path $Path -Force |
        Out-Null
}

Write-Host "`n[2/5] Directory structure created." -ForegroundColor Green

# ------------------------------------------------------------
# 3. Python 3.11 virtual environment
# ------------------------------------------------------------

Write-Host "`n[3/5] Configuring Python environment..."

$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Python)) {

    Write-Host "Creating Python 3.11 virtual environment..."

    & py -3.11 -m venv $Venv

    if ($LASTEXITCODE -ne 0) {
        throw "Virtual environment creation failed."
    }
}

if (-not (Test-Path $Python)) {
    throw "Python executable was not created."
}

$PythonVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"

if ($PythonVersion -ne "3.11") {
    throw "Unexpected virtual environment Python version: $PythonVersion"
}

Write-Host "Python environment verified: $PythonVersion" -ForegroundColor Green

# ------------------------------------------------------------
# 4. Dependencies
# ------------------------------------------------------------

Write-Host "`n[4/5] Preparing dependencies..."

$RequirementsPath = Join-Path $Root "requirements.txt"

$Requirements = @"
# SKYFALL - Desktop and Backend Foundation

# Desktop application
PySide6
qasync

# Configuration and validation
pydantic
pydantic-settings
PyYAML

# HTTP and integrations
httpx

# Excel reporting
openpyxl

# Local application utilities
platformdirs
keyring

# Structured logging
structlog
"@

if (-not (Test-Path $RequirementsPath)) {
    Set-Content -Path $RequirementsPath `
        -Value $Requirements `
        -Encoding UTF8
}
else {
    Write-Host "Existing requirements.txt preserved."
    Write-Host "Review it before installing dependencies."
}

# ------------------------------------------------------------
# 5. Python package structure
# ------------------------------------------------------------

Write-Host "`n[5/5] Creating Python package initialization files..."

$Packages = @(
    "app",
    "app\desktop",
    "app\floating",
    "app\components",

    "backend",
    "backend\core",
    "backend\intelligence",
    "backend\orchestrator",
    "backend\services",

    "integrations",
    "integrations\copilot",
    "integrations\azure",
    "integrations\power_platform",

    "mcp",
    "mcp\servers",
    "mcp\tools",
    "mcp\resources",

    "execution",
    "execution\powershell",
    "execution\python",

    "memory",
    "tests",
    "tests\unit",
    "tests\integration",
    "tests\security"
)

foreach ($Package in $Packages) {

    $InitFile = Join-Path (Join-Path $Root $Package) "__init__.py"

    if (-not (Test-Path $InitFile)) {
        New-Item -ItemType File -Path $InitFile |
            Out-Null
    }
}

# Create a basic README
$Readme = Join-Path $Root "README.md"

if (-not (Test-Path $Readme)) {

    @"
# SKYFALL

Personal Engineering Intelligence Assistant.

## Architecture

- Desktop: PySide6
- Backend: Python
- AI: GitHub Copilot SDK
- Tool integration: MCP
- Memory: SQLite
- Execution: PowerShell and Python

## Local development

Activate the Python environment:

    .\.venv\Scripts\Activate.ps1

Run the application:

    python main.py

## Application structure

See the app, backend, integrations, mcp and execution directories.
"@ | Set-Content -Path $Readme -Encoding UTF8
}

# Create local security exclusions
$GitIgnore = Join-Path $Root ".gitignore"

if (-not (Test-Path $GitIgnore)) {

    @"
.venv/
__pycache__/
*.py[cod]
.env
.env.*
!.env.example
database/*.db
database/*.sqlite*
logs/*
reports/*
"@ | Set-Content -Path $GitIgnore -Encoding UTF8
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "       SKYFALL STRUCTURE READY"
Write-Host "==============================================" -ForegroundColor Green

Write-Host "Root: $Root"
Write-Host "Python: $Python"
Write-Host ""
Write-Host "Next command:"
Write-Host "cd `"$Root`""
Write-Host ".\.venv\Scripts\python.exe -m pip install -r requirements.txt"
Write-Host ""
