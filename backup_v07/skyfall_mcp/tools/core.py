"""Safe, read-only SKYFALL core MCP tools for v0.6."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skyfall_mcp.registry import CapabilityRegistry


APP_VERSION = "0.6.0"


def _registry() -> CapabilityRegistry:
    return CapabilityRegistry.default()


def get_skyfall_status() -> str:
    """Return local SKYFALL status and enabled core capability count; no cloud calls are made."""
    registry = _registry()
    enabled = registry.list(enabled_only=True)
    core_enabled = registry.list(category="core", enabled_only=True)
    workspace_enabled = registry.list(category="workspace", enabled_only=True)
    payload = {
        "application": "SKYFALL",
        "version": APP_VERSION,
        "mcp_server": registry.server.get("name", "SKYFALL Local Intelligence"),
        "mcp_status": "running",
        "operating_mode": "read_only_core_and_workspace_metadata",
        "enabled_tools": len(enabled),
        "enabled_core_tools": len(core_enabled),
        "enabled_workspace_tools": len(workspace_enabled),
        "azure_connector": "not_connected",
        "power_platform_connector": "not_connected",
        "workspace_indexing": "read_only_metadata_index",
        "script_execution": "not_enabled",
        "workspace_ai_metadata_policy": "explicit_per_workspace_opt_in",
        "notes": [
            "This tool reports local application metadata only.",
            "No Azure, Power Platform or script execution was performed.",
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
