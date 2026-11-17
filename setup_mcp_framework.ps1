# SKYFALL v0.5 - Install local MCP framework
# Compatible with Windows PowerShell 5.1 and PowerShell 7.
# Uses the project's existing virtual environment and pip truststore feature.

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Requirements = Join-Path $Root "requirements.txt"
$ScaffoldMcp = Join-Path $Root "mcp"
$LegacyMcp = Join-Path $Root "mcp_workspace_legacy"

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " SKYFALL v0.5 - MCP FRAMEWORK SETUP" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "Project root: $Root"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "SKYFALL virtual environment was not found: $Python. Run the foundation setup first."
}

if (-not (Test-Path -LiteralPath $Requirements -PathType Leaf)) {
    throw "requirements.txt was not found: $Requirements"
}

# The initial SKYFALL scaffold created a top-level folder named 'mcp'.
# That name shadows the third-party MCP SDK package. Preserve it by moving
# it aside; never delete or overwrite it.
if (Test-Path -LiteralPath $ScaffoldMcp -PathType Container) {
    if (Test-Path -LiteralPath $LegacyMcp) {
        throw "Both '$ScaffoldMcp' and '$LegacyMcp' exist. Setup stopped to avoid overwriting either folder. Inspect them manually."
    }

    Write-Host "Preserving the old local MCP scaffold as mcp_workspace_legacy..." -ForegroundColor Yellow
    Rename-Item -LiteralPath $ScaffoldMcp -NewName "mcp_workspace_legacy"
}

# Ensure the official MCP SDK requirement is present without replacing the
# user's existing requirements file or unrelated package pins.
$ExistingRequirementLines = Get-Content -LiteralPath $Requirements
$McpRequirementPresent = $false
foreach ($Line in $ExistingRequirementLines) {
    if ($Line -match '^\s*mcp\s*(?:\[[^\]]+\])?\s*(?:[<>=!~]|$)') {
        $McpRequirementPresent = $true
        break
    }
}

if (-not $McpRequirementPresent) {
    Add-Content -LiteralPath $Requirements -Value "mcp>=2.0,<3.0" -Encoding UTF8
    Write-Host "Added mcp>=2.0,<3.0 to requirements.txt."
}
else {
    Write-Host "An MCP SDK requirement is already present; preserving it."
}

Write-Host ""
Write-Host "Installing the official MCP Python SDK..." -ForegroundColor Cyan
& $Python -m pip install --use-feature=truststore "mcp>=2.0,<3.0"
if ($LASTEXITCODE -ne 0) {
    throw "MCP SDK installation failed. Your requirements file and existing application files have been preserved."
}

Write-Host ""
Write-Host "Verifying installed MCP SDK imports..." -ForegroundColor Cyan
$VerifyCode = @'
import sys
import mcp
from mcp import Client, StdioServerParameters
from mcp.server import MCPServer
print("Python:", sys.executable)
print("MCP package:", getattr(mcp, "__file__", "namespace package"))
print("MCPServer import: OK")
print("Client import: OK")
print("StdioServerParameters import: OK")
'@
& $Python -c $VerifyCode
if ($LASTEXITCODE -ne 0) {
    throw "MCP SDK import verification failed. Check for a remaining local 'mcp' namespace conflict."
}

Write-Host ""
Write-Host "Checking dependency consistency..." -ForegroundColor Cyan
& $Python -m pip check
if ($LASTEXITCODE -ne 0) {
    throw "pip check found dependency conflicts. Review the output before continuing."
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host " SKYFALL MCP SDK INSTALLED" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host "Next: run .\.venv\Scripts\python.exe .\scripts\test_mcp_server.py"
