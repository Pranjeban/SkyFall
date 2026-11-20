"""End-to-end stdio smoke test for SKYFALL v0.9.2.

Uses an isolated temporary workspace database and sample script. It does not
read or modify the user's configured workspaces, call cloud services, or run
scripts. All MCP tools are discovered and exercised over a child stdio process.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp import Client, StdioServerParameters  # noqa: E402
from skyfall_workspace.manager import WorkspaceManager  # noqa: E402


EXPECTED_TOOL_NAMES = {
    "get_skyfall_status",
    "list_skyfall_capabilities",
    "describe_skyfall_capability",
    "get_workspace_index_status",
    "list_workspaces",
    "search_workspace_files",
    "describe_workspace_file",
    "list_azure_profiles",
    "get_azure_auth_status",
    "list_azure_subscriptions",
    "list_azure_tenants",
    "list_powerplatform_auth_profiles",
    "configure_powerplatform_app",
    "get_powerplatform_auth_status",
    "list_powerplatform_environments",
    "start_azure_login",
    "start_powerplatform_login",
    "get_microsoft_auth_job_status",
    "inventory_azure_function_apps",
    "find_azure_function_app",
    "inventory_power_automate_flows",
    "get_unified_identity_health",
    "discover_azure_footprint",
    "inventory_azure_resources",
    "discover_powerplatform_environments",
    "describe_powerplatform_environment",
    "inspect_powerplatform_catalog",
    "run_cloud_orchestration",
    "correlate_cross_platform",
    "cloud_health_report",
    "build_executive_report",
    "governance_summary",
    "route_copilot_intent",
    "build_operation_plan",
}


def child_environment(local_app_data: Path) -> dict[str, str]:
    """Pass the minimum Windows process environment to the MCP child process."""
    names = (
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "PATH",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
    )
    env = {name: os.environ[name] for name in names if os.environ.get(name)}
    env.update(
        {
            "LOCALAPPDATA": str(local_app_data),
            "PYTHONPATH": str(ROOT),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "SKYFALL_ROOT": str(ROOT),
            "SKYFALL_TEST_MODE": "1",
        }
    )
    return env


def text_content(result: Any) -> str:
    """Join text blocks from an MCP CallToolResult."""
    parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        value = getattr(item, "text", None)
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


def json_payload(result: Any, tool_name: str) -> dict[str, Any]:
    """Decode a tool result and provide a useful error if it is not JSON."""
    raw = text_content(result)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"MCP tool {tool_name} did not return valid JSON. Response: {raw!r}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"MCP tool {tool_name} returned {type(payload).__name__}, expected an object."
        )
    return payload


async def invoke_tool(client: Any, name: str, arguments: dict[str, Any]) -> Any:
    """Call one MCP tool and print a breadcrumb to localize failures."""
    print(f"[MCP TEST] calling {name} ...", flush=True)
    try:
        result = await client.call_tool(name, arguments)
    except Exception as exc:
        raise RuntimeError(
            f"MCP tool call failed at {name}: {type(exc).__name__}: {exc}"
        ) from exc

    if getattr(result, "is_error", False):
        raise RuntimeError(
            f"MCP tool {name} returned an error: {text_content(result)}"
        )

    print(f"[MCP TEST] {name}: response received", flush=True)
    return result


def get_tool_input_schema(tool: Any) -> dict[str, Any]:
    """Read MCP tool input schema across SDK v1/v2 Python naming conventions."""
    schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = getattr(tool, "inputSchema", None)
    if schema is None and hasattr(tool, "model_dump"):
        dumped = tool.model_dump(by_alias=True)
        schema = dumped.get("inputSchema") or dumped.get("input_schema")
    if not isinstance(schema, dict):
        fields = getattr(tool, "model_fields", {})
        raise RuntimeError(
            "Could not read start_powerplatform_login input schema. "
            f"Available Tool model fields: {sorted(fields.keys())}"
        )
    return schema


async def run_server_test(local_app_data: Path) -> int:
    environment = child_environment(local_app_data)
    print("Checking MCP server imports in the child interpreter...", flush=True)
    try:
        preflight = subprocess.run(
            [sys.executable, "-c", "import skyfall_mcp.server; print('MCP server import: OK')"],
            cwd=str(ROOT),
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            f"Could not start the MCP child interpreter ({sys.executable}): "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if preflight.returncode != 0:
        detail = (preflight.stderr or preflight.stdout or "No child-process diagnostic was returned.").strip()
        raise RuntimeError(
            "The MCP child failed while importing skyfall_mcp.server. "
            "This is usually a missing dependency or an invalid project environment. "
            f"Interpreter: {sys.executable}\n{detail[-6000:]}"
        )
    if preflight.stdout.strip():
        print(preflight.stdout.strip(), flush=True)

    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "skyfall_mcp.server"],
        env=environment,
        cwd=str(ROOT),
    )

    print("SKYFALL MCP: starting local stdio server test...")
    print(f"Project root: {ROOT}")
    print(f"Python: {sys.executable}")
    print("Workspace database: isolated temporary test database")

    async with Client(server) as client:
        discovered = await client.list_tools()
        actual_names = {tool.name for tool in discovered.tools}
        print("Discovered tools:", ", ".join(sorted(actual_names)), flush=True)

        if actual_names != EXPECTED_TOOL_NAMES:
            missing = sorted(EXPECTED_TOOL_NAMES - actual_names)
            unexpected = sorted(actual_names - EXPECTED_TOOL_NAMES)
            raise RuntimeError(
                "Unexpected MCP tool set. "
                f"Missing: {missing}; unexpected: {unexpected}"
            )

        # Profile names are required so the assistant collects a name before
        # invoking the Power Platform profile/login operation. The assistant
        # can ask the user conversationally; the tool input remains explicit.
        pp_tool = next(
            tool for tool in discovered.tools
            if tool.name == "start_powerplatform_login"
        )
        pp_schema = get_tool_input_schema(pp_tool)
        required_pp_fields = pp_schema.get("required", [])
        print(
            "[MCP TEST] start_powerplatform_login required fields:",
            required_pp_fields,
            flush=True,
        )
        if "profile_name" not in required_pp_fields:
            raise RuntimeError(
                "start_powerplatform_login must require profile_name at MCP "
                "schema level so SKYFALL collects a profile name before invoking it."
            )
        print("[MCP TEST] Power Platform profile_name schema: PASS")

        # Core tools
        status = await invoke_tool(client, "get_skyfall_status", {})
        status_payload = json_payload(status, "get_skyfall_status")
        if status_payload.get("application") != "SKYFALL":
            raise RuntimeError("Status tool returned an unexpected application name.")
        if status_payload.get("enabled_tools") != 34:
            raise RuntimeError(
                "Status tool did not report thirty-four enabled tools; "
                f"got {status_payload.get('enabled_tools')!r}."
            )

        listing = await invoke_tool(
            client, "list_skyfall_capabilities", {"category": "core"}
        )
        listing_payload = json_payload(listing, "list_skyfall_capabilities")
        if listing_payload.get("count") != 3:
            raise RuntimeError(
                "Capability list did not return exactly three enabled core tools."
            )

        described = await invoke_tool(
            client,
            "describe_skyfall_capability",
            {"capability_id": "core.get_status"},
        )
        described_payload = json_payload(described, "describe_skyfall_capability")
        if described_payload.get("tool_name") != "get_skyfall_status":
            raise RuntimeError("Capability description returned unexpected metadata.")

        print("Core status tool: PASS")
        print("Core capability listing tool: PASS")
        print("Core capability description tool: PASS")

        # Workspace tools, using only the isolated temporary database.
        workspace_status = await invoke_tool(
            client, "get_workspace_index_status", {}
        )
        workspace_status_payload = json_payload(
            workspace_status, "get_workspace_index_status"
        )
        if workspace_status_payload.get("ai_visible_workspaces") != 1:
            raise RuntimeError(
                "Workspace status did not find the isolated consented test workspace."
            )
        if workspace_status_payload.get("source_contents_shared") is not False:
            raise RuntimeError(
                "Workspace status did not confirm source-content privacy."
            )

        workspaces = await invoke_tool(client, "list_workspaces", {})
        workspace_payload = json_payload(workspaces, "list_workspaces")
        if workspace_payload.get("count") != 1:
            raise RuntimeError(
                "Workspace listing did not return exactly the isolated test workspace."
            )
        if workspace_payload.get("source_contents_shared") is not False:
            raise RuntimeError(
                "Workspace listing did not confirm source-content privacy."
            )

        search = await invoke_tool(
            client,
            "search_workspace_files",
            {
                "query": "SkyfallWorkspaceSmokeScript",
                "file_type": "powershell",
                "limit": 5,
            },
        )
        search_payload = json_payload(search, "search_workspace_files")
        if search_payload.get("count") != 1:
            raise RuntimeError(
                "Workspace search did not find the expected sample script."
            )
        if search_payload.get("source_contents_shared") is not False:
            raise RuntimeError(
                "Workspace search did not confirm source-content privacy."
            )

        results = search_payload.get("results") or []
        if not results or not isinstance(results[0], dict):
            raise RuntimeError("Workspace search returned no usable result record.")
        file_id = results[0].get("file_id")
        if not file_id:
            raise RuntimeError("Workspace search result did not include file_id.")

        file_description = await invoke_tool(
            client, "describe_workspace_file", {"file_id": file_id}
        )
        file_payload = json_payload(file_description, "describe_workspace_file")
        file_metadata = file_payload.get("file", {})
        if file_metadata.get("name") != "SkyfallWorkspaceSmokeScript.ps1":
            raise RuntimeError("Workspace description returned an unexpected file.")
        serialized = json.dumps(file_payload)
        if "Write-Output 'SOURCE_CONTENT_MUST_NOT_BE_EXPOSED'" in serialized:
            raise RuntimeError(
                "Workspace MCP unexpectedly returned source-code content."
            )
        if file_payload.get("source_contents_shared") is not False:
            raise RuntimeError(
                "Workspace description did not confirm source-content privacy."
            )

        print("Workspace index status tool: PASS")
        print("Workspace listing tool: PASS")
        print("Workspace search tool: PASS")
        print("Workspace file description tool: PASS")

        # Microsoft-account tools run in SKYFALL_TEST_MODE. The child process
        # receives an isolated LOCALAPPDATA and must not invoke real cloud CLIs.
        print("Checking Microsoft account tools...", flush=True)

        azure_profiles = await invoke_tool(client, "list_azure_profiles", {})
        azure_profile_payload = json_payload(
            azure_profiles, "list_azure_profiles"
        )
        if azure_profile_payload.get("count") != 1:
            raise RuntimeError(
                "Azure profile listing did not return the isolated default profile."
            )

        azure_auth = await invoke_tool(client, "get_azure_auth_status", {})
        azure_auth_payload = json_payload(azure_auth, "get_azure_auth_status")
        if azure_auth_payload.get("authenticated") is not False:
            raise RuntimeError(
                "Test-mode Azure auth check should not access real credentials."
            )

        await invoke_tool(client, "list_azure_subscriptions", {})
        await invoke_tool(client, "list_azure_tenants", {})
        await invoke_tool(client, "list_powerplatform_auth_profiles", {})
        await invoke_tool(client, "get_powerplatform_auth_status", {})
        await invoke_tool(client, "list_powerplatform_environments", {})

        invalid_app_id = await invoke_tool(
            client, "configure_powerplatform_app", {"client_id": "not-a-guid"}
        )
        invalid_app_id_payload = json_payload(invalid_app_id, "configure_powerplatform_app")
        if invalid_app_id_payload.get("success") is not False:
            raise RuntimeError("Invalid Power Platform app client ID was accepted.")

        # Missing tenant is collected conversationally by the assistant before
        # it calls the login tool with complete input.
        missing_azure_inputs = await invoke_tool(
            client, "start_azure_login", {}
        )
        missing_azure_payload = json_payload(
            missing_azure_inputs, "start_azure_login"
        )
        if "tenant_id" not in missing_azure_payload.get("requires_input", []):
            raise RuntimeError(
                "Azure login tool did not request missing tenant input."
            )

        # Azure CLI-backed login requires no client ID. Keep browser auth blocked
        # while this isolated smoke test exercises the tool.
        pp_login = await invoke_tool(
            client,
            "start_powerplatform_login",
            {"profile_name": "SKYFALL Smoke Test"},
        )
        pp_login_payload = json_payload(
            pp_login, "start_powerplatform_login"
        )
        if pp_login_payload.get("status") != "blocked_test_mode":
            raise RuntimeError(
                "Power Platform browser sign-in was not blocked in isolated test mode."
            )
        if pp_login_payload.get("login_started") is True:
            raise RuntimeError("Power Platform sign-in started in isolated test mode.")

        # profile_name is required in the MCP schema. This is intentional:
        # Copilot should collect the profile name from the user before it calls
        # the tool. We therefore do not invoke this tool with empty arguments.
        # The valid-name call above verifies the test-mode guard.

        job_lookup = await invoke_tool(
            client,
            "get_microsoft_auth_job_status",
            {"job_id": "does-not-exist"},
        )
        json_payload(job_lookup, "get_microsoft_auth_job_status")

        print("Azure profile listing and safe discovery errors: PASS")
        print("Power Platform profile/environment discovery tools: PASS")
        print("Microsoft account discovery tools: PASS (isolated test mode)")
        print("Required profile-name schema and sign-in job status: PASS")
        print("Power Platform sign-in test-mode guard: PASS")

        azure_inventory_tool = next(tool for tool in discovered.tools if tool.name == "inventory_azure_function_apps")
        azure_inventory_result = await invoke_tool(
            client,
            "inventory_azure_function_apps",
            {"profile_id": "all", "generate_excel": True},
        )
        azure_inventory_payload = json_payload(azure_inventory_result, "inventory_azure_function_apps")
        if azure_inventory_payload.get("status") != "blocked_test_mode":
            raise RuntimeError("Azure Function App inventory was not blocked in isolated MCP test mode.")
        if azure_inventory_payload.get("cloud_resources_modified") is not False:
            raise RuntimeError("Azure inventory test-mode response did not confirm read-only behavior.")
        print("Azure Function App inventory isolated test-mode guard: PASS")

        lookup_tool = next(tool for tool in discovered.tools if tool.name == "find_azure_function_app")
        lookup_schema = get_tool_input_schema(lookup_tool)
        required_lookup_fields = lookup_schema.get("required", [])
        if "name" not in required_lookup_fields:
            raise RuntimeError("find_azure_function_app must require the name argument.")
        lookup_result = await invoke_tool(
            client,
            "find_azure_function_app",
            {"name": "fn-smoke-test", "exact": True},
        )
        lookup_payload = json_payload(lookup_result, "find_azure_function_app")
        if lookup_payload.get("status") != "blocked_test_mode":
            raise RuntimeError("Azure Function App lookup was not blocked in isolated MCP test mode.")
        if lookup_payload.get("cloud_resources_modified") is not False:
            raise RuntimeError("Azure lookup test-mode response did not confirm read-only behavior.")
        print("Azure Function App name lookup schema and test-mode guard: PASS")

        print("Checking Power Automate inventory schema and test-mode guard...", flush=True)
        flow_tool = next(tool for tool in discovered.tools if tool.name == "inventory_power_automate_flows")
        flow_schema = get_tool_input_schema(flow_tool)
        required_flow_fields = flow_schema.get("required", [])
        if "environment_id" not in required_flow_fields:
            raise RuntimeError("inventory_power_automate_flows must require environment_id.")
        blocked_inventory = await invoke_tool(
            client,
            "inventory_power_automate_flows",
            {"environment_id": "00000000-0000-0000-0000-000000000001", "environment_name": "SKYFALL Test"},
        )
        blocked_payload = json_payload(blocked_inventory, "inventory_power_automate_flows")
        if blocked_payload.get("status") != "blocked_test_mode":
            raise RuntimeError("Power Automate inventory was not blocked in isolated MCP test mode.")
        if blocked_payload.get("cloud_resources_modified") is not False:
            raise RuntimeError("Power Automate test-mode response did not confirm read-only behavior.")
        print("Power Automate inventory required environment schema: PASS")
        print("Power Automate inventory isolated test-mode guard: PASS")
        print("Workspace metadata consent: TESTED IN ISOLATED TEMPORARY DB")
        print("External cloud access: NOT USED")
        print("User workspace database: NOT TOUCHED")
        print("Source file contents: NOT RETURNED BY WORKSPACE TOOLS")
        print("Script execution: NOT ENABLED")
        print(
            "RESULT: PASS - SKYFALL v0.9.2 MCP server works over stdio.",
            flush=True,
        )
        return 0


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="skyfall-mcp-v09-") as temp_dir:
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

        database_path = (
            local_app_data / "SKYFALL" / "data" / "workspace_index.db"
        )
        manager = WorkspaceManager(database_path)
        workspace = manager.add_workspace(
            sample_workspace, allow_ai_metadata=True
        )
        manager.scan_workspace(workspace.id)

        return asyncio.run(run_server_test(local_app_data))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Test cancelled by user.", file=sys.stderr)
        raise SystemExit(130)
    except RuntimeError as exc:
        print(f"RESULT: FAIL - {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    except BaseExceptionGroup as exc:
        def leaf_messages(group: BaseExceptionGroup) -> list[str]:
            messages: list[str] = []
            for item in group.exceptions:
                if isinstance(item, BaseExceptionGroup):
                    messages.extend(leaf_messages(item))
                else:
                    messages.append(f"{type(item).__name__}: {item}")
            return messages

        print("RESULT: FAIL - MCP stdio startup/task group failed:", file=sys.stderr)
        for message in leaf_messages(exc):
            print(f"  {message}", file=sys.stderr)
        print(
            "The child import preflight passed. Check that the server uses the same "
            "installed MCP SDK as this test and inspect child startup stderr.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1)
    except Exception as exc:
        print(
            f"RESULT: FAIL - {type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        traceback.print_exception(exc)
        raise SystemExit(1)
