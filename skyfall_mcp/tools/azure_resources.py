"""Read-only Azure resource inventory MCP tools."""

from __future__ import annotations

import json
from typing import Any

from skyfall_cloud.azure_resources import AzureFunctionAppInventory


def inventory_azure_function_apps(
    profile_id: str = "all",
    subscription_ids: list[str] | None = None,
    generate_excel: bool = True,
) -> str:
    """Inventory Azure Function Apps across accessible subscriptions and optionally create an XLSX report.

    Use profile_id='all' to query all registered SKYFALL Azure CLI profiles.
    If the user requests a named subscription or environment, first discover
    subscriptions and pass the verified subscription IDs. This operation is
    read-only against Azure and writes only a local report under reports/Azure.
    """
    payload: dict[str, Any]
    try:
        payload = AzureFunctionAppInventory().inventory(
            profile_id=profile_id,
            subscription_ids=subscription_ids,
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
