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
    find_azure_function_app as _find_azure_function_app,
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
from skyfall_mcp.tools.unified_cloud import (
    build_executive_report as _build_executive_report,
    build_operation_plan as _build_operation_plan,
    cloud_health_report as _cloud_health_report,
    correlate_cross_platform as _correlate_cross_platform,
    describe_powerplatform_environment as _describe_powerplatform_environment,
    discover_azure_footprint as _discover_azure_footprint,
    discover_powerplatform_environments as _discover_powerplatform_environments,
    get_execution_history as _get_execution_history,
    get_unified_identity_health as _get_unified_identity_health,
    governance_summary as _governance_summary,
    inspect_powerplatform_catalog as _inspect_powerplatform_catalog,
    inventory_azure_resources as _inventory_azure_resources,
    plan_execution as _plan_execution,
    route_copilot_intent as _route_copilot_intent,
    run_cloud_orchestration as _run_cloud_orchestration,
)

# MCP stdio uses stdout for protocol frames. All diagnostics must go to stderr.
logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

mcp = MCPServer(
    "SKYFALL Local Intelligence",
    instructions=(
    "SKYFALL v0.9.2 MCP server. Exposes read-only core status/capability tools, "
        "metadata-only workspace discovery, Azure CLI account/subscription discovery, "
        "Power Platform delegated OAuth account/environment discovery, read-only Azure Function App name lookup/inventory and Dataverse cloud-flow inventory with local XLSX reporting, and explicit user-requested "
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


@mcp.tool(title="Configure legacy Power Platform OAuth app")
def configure_powerplatform_app(client_id: str) -> str:
    """Configure the legacy MSAL profile path. New Power Platform profiles use the isolated Azure CLI login."""
    return _configure_powerplatform_app(client_id)


@mcp.tool(title="Connect an Azure account")
def start_azure_login(profile_name: str = "", tenant_id: str = "", profile_id: str = "") -> str:
    """Start Microsoft browser sign-in for a named isolated Azure profile. For a new profile provide profile_name and tenant_id (GUID or tenant domain). For an existing profile provide profile_id. Use get_microsoft_auth_job_status after the user completes sign-in."""
    return _start_azure_login(profile_name, tenant_id, profile_id)


@mcp.tool(title="Connect a Power Platform account")
def start_powerplatform_login(
    profile_name: str,
    tenant: str = "",
) -> str:
    """Start isolated Azure browser sign-in and list accessible Power Platform environments."""
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


@mcp.tool(title="Find a Function App by name")
def find_azure_function_app(
    name: str,
    profile_id: str = "all",
    subscription_ids: list[str] | None = None,
    exact: bool = True,
    max_results: int = 20,
) -> str:
    """Find a Function App by name and return its subscription and non-secret details.

    Use this when the user asks which subscription/resource group/region contains
    a named Function App. Default profile_id to "all" and exact to true. It is
    read-only, generates no report, and never returns app settings or secrets.
    """
    return _find_azure_function_app(name, profile_id, subscription_ids, exact, max_results)


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


@mcp.tool(title="Check unified Microsoft identity health")
def get_unified_identity_health() -> str:
    """Report secret-free health for all registered MSAL identity profiles."""
    return _get_unified_identity_health()


@mcp.tool(title="Discover Azure footprint")
def discover_azure_footprint(profile_id: str = "") -> str:
    """Discover Azure tenants, subscriptions and management groups for one MSAL Azure profile."""
    return _discover_azure_footprint(profile_id)


@mcp.tool(title="Inventory Azure resources")
def inventory_azure_resources(subscription_ids: list[str], categories: str = "") -> str:
    """Inventory spec-defined Azure resource categories across explicit subscription IDs."""
    return _inventory_azure_resources(subscription_ids, categories)


@mcp.tool(title="Discover Power Platform environments")
def discover_powerplatform_environments(profile_id: str = "") -> str:
    """Discover Power Platform environments for one independent MSAL profile."""
    return _discover_powerplatform_environments(profile_id)


@mcp.tool(title="Inspect a Power Platform environment")
def describe_powerplatform_environment(environment_id: str) -> str:
    """Inspect one selected environment's metadata, security flags and capacity."""
    return _describe_powerplatform_environment(environment_id)


@mcp.tool(title="Inspect Power Platform catalog")
def inspect_powerplatform_catalog(environment_id: str, profile_id: str = "") -> str:
    """Inventory flow, app and connection metadata for one selected environment."""
    return _inspect_powerplatform_catalog(environment_id, profile_id)


@mcp.tool(title="Run correlated cloud investigation")
def run_cloud_orchestration(
    azure_profile_id: str = "",
    pp_profile_id: str = "",
    subscription_ids: str = "",
    environment_id: str = "",
) -> str:
    """Run a read-only correlated investigation across both cloud platforms."""
    return _run_cloud_orchestration(azure_profile_id, pp_profile_id, subscription_ids, environment_id)


@mcp.tool(title="Correlate cross-platform inventory")
def correlate_cross_platform(
    azure_resources_json: str = "",
    pp_environments_json: str = "",
) -> str:
    """Correlate supplied Azure and Power Platform inventory JSON."""
    return _correlate_cross_platform(azure_resources_json, pp_environments_json)


@mcp.tool(title="Cloud health and anomaly report")
def cloud_health_report(
    azure_resources_json: str = "",
    pp_environments_json: str = "",
    pp_flows_json: str = "",
    pp_connections_json: str = "",
) -> str:
    """Detect inactive resources, state anomalies and duplicates from supplied JSON."""
    return _cloud_health_report(azure_resources_json, pp_environments_json, pp_flows_json, pp_connections_json)


@mcp.tool(title="Build executive cloud report")
def build_executive_report(
    azure_overview_json: str = "",
    pp_environments_json: str = "",
) -> str:
    """Build a secret-safe executive report from supplied cloud inventory JSON."""
    return _build_executive_report(azure_overview_json, pp_environments_json)


@mcp.tool(title="Governance and audit summary")
def governance_summary() -> str:
    """Report audit counts and the read-only policy boundary."""
    return _governance_summary()


@mcp.tool(title="Route a Copilot request")
def route_copilot_intent(utterance: str) -> str:
    """Map a natural-language request to a read-only capability without executing it."""
    return _route_copilot_intent(utterance)


@mcp.tool(title="Build an operation plan")
def build_operation_plan(
    operation: str,
    provider: str,
    target: str,
    profile_id: str = "",
) -> str:
    """Build and policy-evaluate an operation plan; never executes it."""
    return _build_operation_plan(operation, provider, target, profile_id)


@mcp.tool(title="Plan a capability execution")
def plan_execution(
    operation: str = "",
    tool_name: str = "",
    capability_id: str = "",
    provider: str = "",
    target: str = "",
    profile_id: str = "",
    workspace_id: str = "",
    file_id: str = "",
    query: str = "",
    allow_workspace_fallback: bool = False,
    requires_mutation: bool = False,
) -> str:
    """Resolve, plan and dry-run simulate a request; never starts processes or executes scripts/cloud mutations."""
    return _plan_execution(
        operation=operation,
        tool_name=tool_name,
        capability_id=capability_id,
        provider=provider,
        target=target,
        profile_id=profile_id,
        workspace_id=workspace_id,
        file_id=file_id,
        query=query,
        allow_workspace_fallback=allow_workspace_fallback,
        requires_mutation=requires_mutation,
    )


@mcp.tool(title="Get execution planning history")
def get_execution_history(record_id: str = "", limit: int = 20) -> str:
    """Return bounded, redacted plan/simulation history; never starts processes."""
    return _get_execution_history(record_id=record_id, limit=limit)


if __name__ == "__main__":
    # stdio is the default transport. Do not print startup banners to stdout.
    mcp.run()
