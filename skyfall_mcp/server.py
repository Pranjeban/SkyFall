"""Local stdio MCP server for SKYFALL read-only intelligence capabilities."""

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
from skyfall_mcp.tools.accounts import (
    configure_powerplatform_app as _configure_powerplatform_app,
    get_azure_auth_status as _get_azure_auth_status,
    get_microsoft_auth_job_status as _get_microsoft_auth_job_status,
    get_powerplatform_auth_status as _get_powerplatform_auth_status,
    list_azure_profiles as _list_azure_profiles,
    list_azure_subscriptions as _list_azure_subscriptions,
    list_azure_tenants as _list_azure_tenants,
    list_powerplatform_auth_profiles as _list_powerplatform_auth_profiles,
    list_powerplatform_environments as _list_powerplatform_environments,
    start_azure_login as _start_azure_login,
    start_powerplatform_login as _start_powerplatform_login,
)
from skyfall_mcp.tools.azure_resources import (
    inventory_azure_function_apps as _inventory_azure_function_apps,
)
from skyfall_mcp.tools.powerplatform_resources import (
    inventory_power_automate_flows as _inventory_power_automate_flows,
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
    "SKYFALL v0.9.2 MCP server. Exposes read-only core status/capability tools, "
        "metadata-only workspace discovery, Azure CLI account/subscription discovery, "
        "Power Platform delegated OAuth account/environment discovery, read-only Azure Function App and Dataverse cloud-flow inventory with local XLSX reporting, and explicit user-requested "
    "interactive Microsoft sign-in jobs. Azure profiles are isolated by AZURE_CONFIG_DIR. "
    "Login tools may open a Microsoft sign-in page only when the user explicitly asks "
    "to connect or sign in. They do not create, update or delete cloud resources. "
    "No tokens, secrets, arbitrary shell execution or script execution are exposed."
    ),
    log_level="WARNING",
)


@mcp.tool(title="Check SKYFALL status")
def get_skyfall_status() -> str:
    """Return SKYFALL local runtime status and currently enabled core tools."""
    return _get_skyfall_status()


@mcp.tool(title="Browse available capabilities")
def list_skyfall_capabilities(category: str = "all") -> str:
    """List capabilities registered and enabled in SKYFALL. Optionally filter by category."""
    return _list_skyfall_capabilities(category)


@mcp.tool(title="Explain a capability")
def describe_skyfall_capability(capability_id: str) -> str:
    """Describe a capability using its exact registry ID, such as core.get_status."""
    return _describe_skyfall_capability(capability_id)


@mcp.tool(title="Check workspace indexing")
def get_workspace_index_status() -> str:
    """Return aggregate index status for workspaces explicitly shared with Copilot."""
    return _get_workspace_index_status()


@mcp.tool(title="Browse approved workspaces")
def list_workspaces() -> str:
    """List workspaces whose filenames and extracted metadata the user approved for Copilot."""
    return _list_workspaces()


@mcp.tool(title="Find scripts and files")
def search_workspace_files(
    query: str,
    file_type: str = "all",
    workspace_id: str = "",
    limit: int = 20,
) -> str:
    """Search filenames and metadata only in explicitly shared, indexed workspaces."""
    return _search_workspace_files(query, file_type, workspace_id, limit)


@mcp.tool(title="Inspect script or file metadata")
def describe_workspace_file(file_id: str) -> str:
    """Describe one indexed file using static metadata; source code is never returned."""
    return _describe_workspace_file(file_id)


@mcp.tool(title="Browse Azure accounts")
def list_azure_profiles() -> str:
    """List local SKYFALL Azure CLI profile metadata without credential material."""
    return _list_azure_profiles()


@mcp.tool(title="Check Azure connection")
def get_azure_auth_status(profile_id: str = "all") -> str:
    """Check sign-in status and non-secret account metadata for an Azure CLI profile."""
    return _get_azure_auth_status(profile_id)


@mcp.tool(title="View Azure subscriptions")
def list_azure_subscriptions(profile_id: str = "all", refresh: bool = False) -> str:
    """List accessible subscriptions in an Azure CLI profile; refresh is read-only."""
    return _list_azure_subscriptions(profile_id, refresh)


@mcp.tool(title="View Azure tenants")
def list_azure_tenants(profile_id: str = "all", refresh: bool = False) -> str:
    """List tenant IDs represented in an Azure CLI profile's subscription cache."""
    return _list_azure_tenants(profile_id, refresh)


@mcp.tool(title="Browse Power Platform accounts")
def list_powerplatform_auth_profiles() -> str:
    """List saved SKYFALL-local Microsoft OAuth account profiles."""
    return _list_powerplatform_auth_profiles()


@mcp.tool(title="Check Power Platform connection")
def get_powerplatform_auth_status() -> str:
    """Report the selected SKYFALL Microsoft OAuth profile without exposing tokens."""
    return _get_powerplatform_auth_status()


@mcp.tool(title="View Power Platform environments")
def list_powerplatform_environments() -> str:
    """List environments available to the selected saved Microsoft account."""
    return _list_powerplatform_environments()


@mcp.tool(title="Configure Power Platform app")
def configure_powerplatform_app(client_id: str) -> str:
    """Save the public client ID of a registered Microsoft Entra desktop app. Never provide a client secret."""
    return _configure_powerplatform_app(client_id)


@mcp.tool(title="Connect an Azure account")
def start_azure_login(profile_name: str = "", tenant_id: str = "", profile_id: str = "") -> str:
    """Start Microsoft browser sign-in for a named isolated Azure profile. For a new profile provide profile_name and tenant_id (GUID or tenant domain). For an existing profile provide profile_id. Use get_microsoft_auth_job_status after the user completes sign-in."""
    return _start_azure_login(profile_name, tenant_id, profile_id)


@mcp.tool(title="Connect a Power Platform account")
def start_powerplatform_login(
    profile_name: str,
    tenant: str = "organizations",
) -> str:
    """Start browser sign-in and save a per-SKYFALL Microsoft OAuth account profile."""
    return _start_powerplatform_login(profile_name, tenant)


@mcp.tool(title="Discover Azure Function Apps")
def inventory_azure_function_apps(
    profile_id: str = "all",
    subscription_ids: list[str] | None = None,
    generate_excel: bool = True,
) -> str:
    """Discover Azure Function Apps across accessible subscriptions and optionally generate a detailed local Excel workbook.

    This is read-only against Azure. It never reads app settings, connection
    strings, publishing profiles, host keys, function keys or other secrets.
    The XLSX output is written only beneath SKYFALL's local reports/Azure folder.
    """
    return _inventory_azure_function_apps(profile_id, subscription_ids, generate_excel)


@mcp.tool(title="Check Microsoft sign-in progress")
def get_microsoft_auth_job_status(job_id: str) -> str:
    """Check a started Azure or Power Platform sign-in job and return discovered non-secret tenant, subscription and environment metadata after completion."""
    return _get_microsoft_auth_job_status(job_id)


@mcp.tool(title="Generate Power Automate flow inventory")
def inventory_power_automate_flows(
    environment_id: str,
    environment_name: str = "",
    generate_excel: bool = True,
) -> str:
    """Discover cloud-flow metadata in one explicitly selected environment.

    Uses the selected Microsoft OAuth profile and creates a local Excel report.
    Flow definitions, connection details and secrets are excluded.
    """
    return _inventory_power_automate_flows(environment_id, environment_name, generate_excel)


if __name__ == "__main__":
    # stdio is the default transport. Do not print startup banners to stdout.
    mcp.run()
