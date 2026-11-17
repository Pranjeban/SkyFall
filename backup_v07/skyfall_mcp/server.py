"""Local stdio MCP server for SKYFALL core and metadata-only workspace tools."""

from __future__ import annotations

import logging
import sys

from mcp.server import MCPServer

from skyfall_mcp.tools.workspace import (
    describe_workspace_file as _describe_workspace_file,
    get_workspace_index_status as _get_workspace_index_status,
    list_workspaces as _list_workspaces,
    search_workspace_files as _search_workspace_files,
)
from skyfall_mcp.tools.core import (
    describe_skyfall_capability as _describe_skyfall_capability,
    get_skyfall_status as _get_skyfall_status,
    list_skyfall_capabilities as _list_skyfall_capabilities,
)

# MCP stdio uses stdout for protocol frames. All diagnostics must go to stderr.
logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

mcp = MCPServer(
    "SKYFALL Local Intelligence",
    instructions=(
        "SKYFALL v0.6 MCP server. Exposes read-only core status/capability tools "
        "and metadata-only workspace discovery. Workspace metadata is visible "
        "to Copilot only after explicit per-workspace user consent in the local "
        "desktop UI. Source file contents, detected secret-bearing files, cloud "
        "accounts, shell commands and script execution are not exposed."
    ),
    log_level="WARNING",
)


@mcp.tool(title="Get SKYFALL status")
def get_skyfall_status() -> str:
    """Return SKYFALL local runtime status and currently enabled core tools."""
    return _get_skyfall_status()


@mcp.tool(title="List SKYFALL capabilities")
def list_skyfall_capabilities(category: str = "all") -> str:
    """List capabilities registered and enabled in SKYFALL. Optionally filter by category."""
    return _list_skyfall_capabilities(category)


@mcp.tool(title="Describe a SKYFALL capability")
def describe_skyfall_capability(capability_id: str) -> str:
    """Describe a capability using its exact registry ID, such as core.get_status."""
    return _describe_skyfall_capability(capability_id)


@mcp.tool(title="Get workspace index status")
def get_workspace_index_status() -> str:
    """Return aggregate index status for workspaces explicitly shared with Copilot."""
    return _get_workspace_index_status()


@mcp.tool(title="List AI-approved workspaces")
def list_workspaces() -> str:
    """List workspaces whose filenames and extracted metadata the user approved for Copilot."""
    return _list_workspaces()


@mcp.tool(title="Search workspace files")
def search_workspace_files(
    query: str,
    file_type: str = "all",
    workspace_id: str = "",
    limit: int = 20,
) -> str:
    """Search filenames and metadata only in explicitly shared, indexed workspaces."""
    return _search_workspace_files(query, file_type, workspace_id, limit)


@mcp.tool(title="Describe indexed workspace file")
def describe_workspace_file(file_id: str) -> str:
    """Describe one indexed file using static metadata; source code is never returned."""
    return _describe_workspace_file(file_id)


if __name__ == "__main__":
    # stdio is the default transport. Do not print startup banners to stdout.
    mcp.run()
