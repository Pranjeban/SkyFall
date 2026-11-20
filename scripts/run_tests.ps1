<#
.SYNOPSIS
    Run the Skyfall test suite using the venv_skyfall interpreter.

.DESCRIPTION
    Activates (resolves) the venv_skyfall virtual environment located at the
    repository root and runs pytest against the tests/ directory with sensible
    defaults. Extra arguments are forwarded to pytest.

.USAGE
    .\scripts\run_tests.ps1
    .\scripts\run_tests.ps1 -Args "-k integration -v"
    .\scripts\run_tests.ps1 tests/unit
#>
param(
    [string]$Args = "",
    [string]$Target = "tests/"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python  = Join-Path $repoRoot "venv_skyfall\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Interpreter not found: $python. Create it with: py -3.11 -m venv `"$repoRoot\venv_skyfall`""
    exit 1
}

Write-Host "Using interpreter: $python" -ForegroundColor Cyan
Write-Host "Running: pytest $Target $Args" -ForegroundColor Cyan

$pytestArgs = @("-m", "pytest", $Target) + ($Args -split '\s+' | Where-Object { $_ })
& $python @pytestArgs
$exit = $LASTEXITCODE
Write-Host "pytest exit code: $exit" -ForegroundColor $(if ($exit -eq 0) { "Green" } else { "Red" })
exit $exit
