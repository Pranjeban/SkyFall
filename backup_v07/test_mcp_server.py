"""End-to-end stdio smoke test for SKYFALL v0.6 MCP.

Uses an isolated temporary workspace database and sample script. It does not
read or modify the user's configured workspaces, call cloud services, or run
scripts. All MCP tools are discovered and exercised over a child stdio process.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# Running a file directly sets sys.path[0] to the scripts/ directory,
# not the project root. Add the SKYFALL root before importing project packages.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp import Client, StdioServerParameters
from skyfall_workspace.manager import WorkspaceManager


def child_environment(local_app_data: Path) -> dict[str, str]:
    """Pass only the process variables needed by Python on Windows."""
    names = (
        "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH",
        "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA",
    )
    env = {name: os.environ[name] for name in names if os.environ.get(name)}
    env.update({
        "LOCALAPPDATA": str(local_app_data),
        "PYTHONPATH": str(ROOT),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "SKYFALL_ROOT": str(ROOT),
    })
    return env


def text_content(result) -> str:
    parts = []
    for item in getattr(result, "content", []) or []:
        value = getattr(item, "text", None)
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


async def run_server_test(local_app_data: Path) -> int:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "skyfall_mcp.server"],
        env=child_environment(local_app_data),
        cwd=str(ROOT),
    )

    print("SKYFALL MCP: starting local stdio server test...")
    print(f"Project root: {ROOT}")
    print(f"Python: {sys.executable}")
    print("Workspace database: isolated temporary test database")

    async with Client(server) as client:
        discovered = await client.list_tools()
        actual_names = {tool.name for tool in discovered.tools}
        expected_names = {
            "get_skyfall_status",
            "list_skyfall_capabilities",
            "describe_skyfall_capability",
            "get_workspace_index_status",
            "list_workspaces",
            "search_workspace_files",
            "describe_workspace_file",
        }

        print("Discovered tools:", ", ".join(sorted(actual_names)))
        if actual_names != expected_names:
            raise RuntimeError(
                "Unexpected MCP tool set. "
                f"Expected {sorted(expected_names)}, got {sorted(actual_names)}"
            )

        status = await client.call_tool("get_skyfall_status", {})
        if status.is_error:
            raise RuntimeError(f"get_skyfall_status failed: {text_content(status)}")
        status_payload = json.loads(text_content(status))
        if status_payload.get("application") != "SKYFALL":
            raise RuntimeError("Status tool returned an unexpected application name.")
        if status_payload.get("enabled_tools") != 7:
            raise RuntimeError("Status tool did not report seven enabled tools.")

        listing = await client.call_tool(
            "list_skyfall_capabilities", {"category": "core"}
        )
        if listing.is_error:
            raise RuntimeError(f"list_skyfall_capabilities failed: {text_content(listing)}")
        listing_payload = json.loads(text_content(listing))
        if listing_payload.get("count") != 3:
            raise RuntimeError("Capability list did not return exactly three enabled core tools.")

        described = await client.call_tool(
            "describe_skyfall_capability", {"capability_id": "core.get_status"}
        )
        if described.is_error:
            raise RuntimeError(f"describe_skyfall_capability failed: {text_content(described)}")
        described_payload = json.loads(text_content(described))
        if described_payload.get("tool_name") != "get_skyfall_status":
            raise RuntimeError("Capability description returned unexpected metadata.")

        print("Core status tool: PASS")
        print("Core capability listing tool: PASS")
        print("Core capability description tool: PASS")

        workspace_status = await client.call_tool("get_workspace_index_status", {})
        if workspace_status.is_error:
            raise RuntimeError(f"get_workspace_index_status failed: {text_content(workspace_status)}")
        status_payload = json.loads(text_content(workspace_status))
        if status_payload.get("ai_visible_workspaces") != 1:
            raise RuntimeError("Workspace status did not find the isolated consented test workspace.")
        if status_payload.get("source_contents_shared") is not False:
            raise RuntimeError("Workspace status did not confirm source-content privacy.")

        workspaces = await client.call_tool("list_workspaces", {})
        if workspaces.is_error:
            raise RuntimeError(f"list_workspaces failed: {text_content(workspaces)}")
        workspace_payload = json.loads(text_content(workspaces))
        if workspace_payload.get("count") != 1:
            raise RuntimeError("Workspace listing did not return exactly the isolated test workspace.")
        if workspace_payload.get("source_contents_shared") is not False:
            raise RuntimeError("Workspace listing did not confirm source-content privacy.")

        search = await client.call_tool(
            "search_workspace_files",
            {"query": "SkyfallWorkspaceSmokeScript", "file_type": "powershell", "limit": 5},
        )
        if search.is_error:
            raise RuntimeError(f"search_workspace_files failed: {text_content(search)}")
        search_payload = json.loads(text_content(search))
        if search_payload.get("count") != 1:
            raise RuntimeError("Workspace search did not find the expected sample script.")
        if search_payload.get("source_contents_shared") is not False:
            raise RuntimeError("Workspace search did not confirm source-content privacy.")

        file_id = search_payload["results"][0]["file_id"]
        file_description = await client.call_tool(
            "describe_workspace_file", {"file_id": file_id}
        )
        if file_description.is_error:
            raise RuntimeError(f"describe_workspace_file failed: {text_content(file_description)}")
        file_payload = json.loads(text_content(file_description))
        if file_payload.get("file", {}).get("name") != "SkyfallWorkspaceSmokeScript.ps1":
            raise RuntimeError("Workspace description returned an unexpected file.")
        serialized = json.dumps(file_payload)
        if "Write-Output 'SOURCE_CONTENT_MUST_NOT_BE_EXPOSED'" in serialized:
            raise RuntimeError("Workspace MCP unexpectedly returned source-code content.")
        if file_payload.get("source_contents_shared") is not False:
            raise RuntimeError("Workspace description did not confirm source-content privacy.")

        print("Workspace index status tool: PASS")
        print("Workspace listing tool: PASS")
        print("Workspace search tool: PASS")
        print("Workspace file description tool: PASS")
        print("Workspace metadata consent: TESTED IN ISOLATED TEMPORARY DB")
        print("External cloud access: NOT USED")
        print("User workspace database: NOT TOUCHED")
        print("Source file contents: NOT RETURNED BY WORKSPACE TOOLS")
        print("Script execution: NOT ENABLED")
        print("RESULT: PASS - SKYFALL v0.6 MCP server works over stdio.")
        return 0


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="skyfall-mcp-v06-") as temp_dir:
        temp_root = Path(temp_dir)
        local_app_data = temp_root / "LocalAppData"
        local_app_data.mkdir(parents=True)
        sample_workspace = temp_root / "sample_workspace"
        sample_workspace.mkdir()
        sample_script = sample_workspace / "SkyfallWorkspaceSmokeScript.ps1"
        sample_script.write_text(
            "param([string]$EnvironmentName)\n"
            "function Get-SkyfallWorkspaceSmokeInventory { }\n"
            "Write-Output 'SOURCE_CONTENT_MUST_NOT_BE_EXPOSED'\n",
            encoding="utf-8",
        )

        database_path = local_app_data / "SKYFALL" / "data" / "workspace_index.db"
        manager = WorkspaceManager(database_path)
        workspace = manager.add_workspace(sample_workspace, allow_ai_metadata=True)
        manager.scan_workspace(workspace.id)

        return asyncio.run(run_server_test(local_app_data))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Test cancelled by user.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"RESULT: FAIL - {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)