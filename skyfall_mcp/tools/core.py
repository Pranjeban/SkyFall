"""SKYFALL core MCP tools for v0.9.2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skyfall_mcp.registry import CapabilityRegistry


APP_VERSION = "0.9.2"


def _registry() -> CapabilityRegistry:
    return CapabilityRegistry.default()


def get_skyfall_status() -> str:
    """Return local SKYFALL status and enabled core capability count; no cloud calls are made."""
    registry = _registry()
    enabled = registry.list(enabled_only=True)
    core_enabled = registry.list(category="core", enabled_only=True)
    workspace_enabled = registry.list(category="workspace", enabled_only=True)
    azure_enabled = registry.list(category="azure", enabled_only=True)
    azure_resource_enabled = registry.list(category="azure_resources", enabled_only=True)
    power_platform_enabled = registry.list(category="power_platform", enabled_only=True)
    power_platform_resource_enabled = registry.list(category="power_platform_resources", enabled_only=True)
    authentication_enabled = registry.list(category="authentication", enabled_only=True)
    payload = {
        "application": "SKYFALL",
        "version": APP_VERSION,
        "mcp_server": registry.server.get("name", "SKYFALL Local Intelligence"),
        "mcp_status": "running",
        "operating_mode": "read_only_discovery_with_explicit_interactive_authentication",
        "enabled_tools": len(enabled),
        "enabled_core_tools": len(core_enabled),
        "enabled_workspace_tools": len(workspace_enabled),
        "enabled_azure_discovery_tools": len(azure_enabled),
        "enabled_azure_resource_tools": len(azure_resource_enabled),
        "enabled_power_platform_discovery_tools": len(power_platform_enabled),
        "enabled_power_platform_resource_tools": len(power_platform_resource_enabled),
        "enabled_authentication_tools": len(authentication_enabled),
        "azure_connector": "read_only_account_subscription_general_resource_and_function_app_inventory_available",
        "power_platform_connector": "read_only_profile_environment_power_apps_and_cloud_flow_inventory_available",
        "workspace_indexing": "read_only_metadata_index",
        "script_execution": "not_enabled",
        "cloud_resource_modification": "not_enabled",
        "workspace_ai_metadata_policy": "explicit_per_workspace_opt_in",
        "notes": [
            "This tool reports local application metadata only.",
            "The status tool itself does not perform cloud discovery. Dedicated Microsoft discovery tools are available separately.",
            "No cloud resources were modified and no scripts were executed.",
            "Azure Function App inventory is read-only and can write a local XLSX report; app settings and keys are excluded.",
            "General Azure resource inventory returns only identifier, type, location, resource group, subscription, SKU and managed-by metadata; arbitrary properties and tags are excluded.",
            "Power Automate cloud-flow inventory is read-only and writes a local XLSX report; flow definitions and connection details are excluded.",
            "Power Apps inventory is read-only through the Power Platform API and writes only local app metadata reports; definitions, connections and secrets are excluded.",
            "Interactive Microsoft sign-in tools run only after an explicit user request; they do not modify cloud resources.",
            "Workspace indexing is local; Copilot can receive only metadata for roots the user explicitly approved.",
            "Source file contents are not persisted in the workspace index or returned by workspace MCP tools.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def list_skyfall_capabilities(category: str = "all") -> str:
    """List enabled capabilities in SKYFALL's local registry, optionally filtered by category."""
    registry = _registry()
    capabilities = registry.list(category=category, enabled_only=True)
    payload: dict[str, Any] = {
        "count": len(capabilities),
        "category_filter": (category or "all").strip().lower(),
        "capabilities": [item.to_dict() for item in capabilities],
        "scope": "registered_and_enabled_only",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def describe_skyfall_capability(capability_id: str) -> str:
    """Describe one exact capability ID from the local SKYFALL registry."""
    registry = _registry()
    try:
        capability = registry.get(capability_id)
    except KeyError as exc:
        return json.dumps({"error": str(exc), "available_ids": [c.id for c in registry.list()]}, indent=2)
    return json.dumps(capability.to_dict(), ensure_ascii=False, indent=2)
