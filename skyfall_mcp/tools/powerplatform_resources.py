"""Read-only Power Automate inventory MCP tool."""

from __future__ import annotations

import json
from typing import Any

from skyfall_cloud.powerplatform_resources import (
    PowerPlatformAppInventory,
    PowerPlatformFlowInventory,
    PowerPlatformSolutionInventory,
)


def inventory_power_automate_flows(
    environment_id: str,
    environment_name: str = "",
    generate_excel: bool = True,
) -> str:
    """Discover cloud-flow metadata in one explicitly selected environment.

    The operation uses the selected Microsoft OAuth profile and returns allow-listed metadata,
    and optionally writes a local Excel report. Flow definitions, action payloads,
    connection details, credentials and secrets are not retrieved.
    """
    try:
        payload: dict[str, Any] = PowerPlatformFlowInventory().inventory(
            environment_id=environment_id,
            environment_name=environment_name,
            generate_excel=generate_excel,
        )
    except (ValueError, KeyError) as exc:
        payload = {
            "success": False,
            "status": "invalid_request",
            "error": str(exc),
            "cloud_resources_modified": False,
            "secrets_returned": False,
        }
    except Exception as exc:
        payload = {
            "success": False,
            "status": "failed",
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
            "cloud_resources_modified": False,
            "secrets_returned": False,
        }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def inventory_power_apps(
    environment_id: str,
    profile_id: str = "",
    generate_excel: bool = True,
) -> str:
    """Inventory Power Apps metadata in one explicitly selected accessible environment."""
    try:
        payload: dict[str, Any] = PowerPlatformAppInventory().inventory(
            environment_id=environment_id,
            profile_id=profile_id or None,
            generate_excel=generate_excel,
        )
    except (ValueError, KeyError) as exc:
        payload = {
            "success": False,
            "status": "invalid_request",
            "error": str(exc),
            "cloud_resources_modified": False,
            "secrets_returned": False,
        }
    except Exception as exc:
        payload = {
            "success": False,
            "status": "failed",
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
            "cloud_resources_modified": False,
            "secrets_returned": False,
        }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def inventory_power_platform_solutions(
    environment_id: str,
    profile_id: str = "",
    generate_excel: bool = True,
) -> str:
    """Inventory visible solution metadata in one verified Dataverse environment."""
    try:
        payload: dict[str, Any] = PowerPlatformSolutionInventory().inventory(
            environment_id=environment_id,
            profile_id=profile_id or None,
            generate_excel=generate_excel,
        )
    except (ValueError, KeyError) as exc:
        payload = {
            "success": False,
            "status": "invalid_request",
            "error": str(exc),
            "cloud_resources_modified": False,
            "secrets_returned": False,
        }
    except Exception as exc:
        payload = {
            "success": False,
            "status": "failed",
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
            "cloud_resources_modified": False,
            "secrets_returned": False,
        }
    return json.dumps(payload, ensure_ascii=False, indent=2)
