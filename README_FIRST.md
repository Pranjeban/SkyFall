# SKYFALL v0.9.1 — Upgrade instructions

This is an incremental upgrade for the existing local SKYFALL project. It preserves the virtual environment, Copilot runtime/session data, SQLite conversation history, workspace index, Azure profiles, PAC CLI profiles and generated reports.

## Target directory

`C:\Users\pkara\Documents\Skyfall\`

Close SKYFALL completely before applying the update.

## 1. Back up the files that this update replaces

Run from the SKYFALL project root:

```powershell
cd C:\Users\pkara\Documents\Skyfall

$Backup = ".\backup_before_v0.9.1"
New-Item -ItemType Directory -Path $Backup -Force | Out-Null

$Files = @(
    "app\desktop\main_window.py",
    "app\desktop\theme.py",
    "configuration\capabilities.json",
    "integrations\copilot\copilot_service.py",
    "skyfall_cloud\__init__.py",
    "skyfall_cloud\powerplatform.py",
    "skyfall_cloud\powerplatform_resources.py",
    "skyfall_mcp\server.py",
    "skyfall_mcp\tools\core.py",
    "scripts\test_mcp_server.py",
    "tests\unit\test_core_mcp_tools.py",
    "tests\unit\test_powerplatform_discovery.py",
    "VERSION.txt"
)

foreach ($File in $Files) {
    if (Test-Path $File) {
        $Destination = Join-Path $Backup $File
        $Parent = Split-Path $Destination -Parent
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
        Copy-Item -LiteralPath $File -Destination $Destination -Force
    }
}

Write-Host "Backup created at $Backup"
```

## 2. Install

1. Extract `SKYFALL_PowerPlatform_UI_Refinement_v0.9.1.zip` directly into the project root.
2. Allow the included application/source files to overwrite matching files.
3. Do not delete or recreate `.venv`.
4. No new Python package is required.

## 3. Validate

```powershell
cd C:\Users\pkara\Documents\Skyfall

.\.venv\Scripts\Activate.ps1

python -m compileall -q .
python -m unittest discover -s .\tests\unit -v
python .\scripts\test_mcp_server.py
```

Then start the desktop application:

```powershell
python .\main.py
```

## 4. What to verify

- Open **Power Platform** and confirm the active PAC profile is shown.
- Environment discovery should first try JSON, then fall back to `pac admin list` table output if needed.
- If the table fallback is used, the UI should show discovered environments and a small explanatory notice rather than a JSON parse error.
- Open **Flow Inventory**. The page should show four summary cards and a useful empty state instead of a large blank table.
- Select an environment and generate the report. The flow preview table should appear only when records are available.
- If environment discovery still fails, the page should show an actionable message and a **Retry environment discovery** button.
- The Capabilities page should display readable cards rather than narrow empty bars.
- Report filenames should remain descriptive and date-based.

## 5. Diagnostic fallback if environment discovery still fails

Run these commands in PowerShell and share the output with secrets and tenant-sensitive identifiers redacted:

```powershell
pac auth list
pac admin list --json
pac admin list
```

The last command is the documented standard table output. SKYFALL v0.9.1 attempts it automatically when JSON parsing is unavailable.

## Notes

Environment visibility is determined by the active PAC CLI profile and the permissions of the signed-in account. `pac admin list` may require Power Platform administrative permissions. SKYFALL does not silently switch PAC CLI profiles.
