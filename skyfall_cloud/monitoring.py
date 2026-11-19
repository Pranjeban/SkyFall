"""Read-only monitoring and anomaly detection skeleton for SKYFALL v1.0.1.

The classes in this module analyse metadata that has already been discovered
through SKYFALL's read-only Azure and Power Platform inventory paths. They do
not perform cloud writes, do not read secrets, and never mutate resources.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping

_UNHEALTHY_STATES = {"failed", "unavailable", "degraded", "stopped", "disabled", "suspended", "unknown"}
_FAILED_FLOW_STATES = {"failed", "cancelled", "canceled", "timedout", "timed out", "faulted"}
_INACTIVE_FLOW_STATES = {"disabled", "stopped", "suspended", "off"}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _first(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    # support dotted paths one level deep
    for key in keys:
        if "." in key:
            current: Any = mapping
            ok = True
            for part in key.split("."):
                if isinstance(current, Mapping) and part in current:
                    current = current.get(part)
                else:
                    ok = False
                    break
            if ok and current is not None:
                return current
    return None


def _name_of(item: Mapping[str, Any]) -> str:
    return str(_first(item, ("name", "resource_name", "flow_name", "display_name", "id", "resource_id", "flow_id")) or "")


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class AzureResourceHealthChecker:
    """Read-only checker for Azure resource health metadata."""

    def __init__(
        self,
        *,
        client: Any = None,
        profile_manager: Any = None,
        http_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.client = client
        self.profile_manager = profile_manager
        self.http_client_factory = http_client_factory

    def check(self, items: Any = None, *, resources: Any = None, client: Any = None, **_kwargs: Any) -> dict[str, Any]:
        resolved_client = client or self.client
        data = items if items is not None else resources
        if data is None and resolved_client is not None:
            for method_name in ("list_resources", "list", "get_resources", "inventory"):
                method = getattr(resolved_client, method_name, None)
                if callable(method):
                    try:
                        result = method()
                    except TypeError:
                        result = method(profile_id="all")
                    if isinstance(result, dict):
                        data = result.get("resources") or result.get("items") or result.get("data") or []
                    else:
                        data = result
                    break
        records = _as_list(data)
        results: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            status = _first(record, ("health_status", "healthState", "status", "state", "provisioning_state", "provisioningState"))
            status_text = str(status or "").strip()
            healthy = status_text.casefold() not in _UNHEALTHY_STATES and bool(status_text)
            results.append(
                {
                    "name": _name_of(record),
                    "resource_id": _first(record, ("resource_id", "id", "resourceId")),
                    "status": status_text or "Unknown",
                    "healthy": healthy,
                    "issues": [] if healthy else [f"resource reports {status_text or 'unknown'} status"],
                }
            )
        return {
            "success": True,
            "operation": "azure_resource_health_check",
            "checked_count": len(results),
            "unhealthy_count": sum(1 for item in results if not item["healthy"]),
            "results": results,
            "cloud_resources_modified": False,
            "secrets_returned": False,
        }

    check_health = check
    check_resources = check


class FunctionAppAvailabilityChecker:
    """Read-only availability checker for Azure Function Apps."""

    def __init__(self, *, client: Any = None, profile_manager: Any = None) -> None:
        self.client = client
        self.profile_manager = profile_manager

    def check(self, items: Any = None, *, function_apps: Any = None, apps: Any = None, client: Any = None, **_kwargs: Any) -> dict[str, Any]:
        resolved_client = client or self.client
        data = items if items is not None else (function_apps if function_apps is not None else apps)
        if data is None and resolved_client is not None:
            for method_name in ("list_function_apps", "list", "inventory"):
                method = getattr(resolved_client, method_name, None)
                if callable(method):
                    try:
                        result = method()
                    except TypeError:
                        result = method(profile_id="all")
                    if isinstance(result, dict):
                        data = result.get("function_apps") or result.get("apps") or result.get("items") or result.get("data") or []
                    else:
                        data = result
                    break
        records = _as_list(data)
        results: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            state = str(_first(record, ("state", "status", "availabilityState")) or "").strip()
            available = state.casefold() in {"running", "started", "available", "ready", "success"}
            if not state:
                available = False
                state = "Unknown"
            results.append(
                {
                    "name": _name_of(record),
                    "resource_id": _first(record, ("resource_id", "id", "resourceId")),
                    "state": state,
                    "available": available,
                    "issues": [] if available else [f"function app is {state}"],
                }
            )
        return {
            "success": True,
            "operation": "function_app_availability_check",
            "checked_count": len(results),
            "unavailable_count": sum(1 for item in results if not item["available"]),
            "results": results,
            "cloud_resources_modified": False,
            "secrets_returned": False,
        }

    check_availability = check
    check_function_apps = check


class PowerAutomateFailureDetector:
    """Metadata-only detector for failed/suspended Power Automate cloud flows."""

    def __init__(self, *, api: Any = None, client: Any = None) -> None:
        self.api = api
        self.client = client

    def detect(self, items: Any = None, *, flows: Any = None, client: Any = None, api: Any = None, **_kwargs: Any) -> dict[str, Any]:
        resolved_client = client or api or self.client or self.api
        data = items if items is not None else flows
        if data is None and resolved_client is not None:
            for method_name in ("list_flows", "list", "inventory"):
                method = getattr(resolved_client, method_name, None)
                if callable(method):
                    try:
                        result = method()
                    except TypeError:
                        try:
                            result = method(profile_id=None)
                        except TypeError:
                            result = method(None)
                    if isinstance(result, dict):
                        data = result.get("flows") or result.get("items") or result.get("data") or result.get("value") or []
                    else:
                        data = result
                    break
        records = _as_list(data)
        failures: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            status = str(_first(record, ("status", "state", "flowState")) or "").strip()
            lowered = status.casefold()
            entry = {
                "name": _name_of(record),
                "flow_id": _first(record, ("flow_id", "id", "workflowId", "flowId")),
                "status": status or "Unknown",
                "metadata_only": True,
            }
            if lowered in _FAILED_FLOW_STATES:
                failures.append(entry)
            elif lowered in _INACTIVE_FLOW_STATES:
                warnings.append(entry)
        return {
            "success": True,
            "operation": "power_automate_failure_detection",
            "checked_count": len(records),
            "failure_count": len(failures),
            "warning_count": len(warnings),
            "failures": failures,
            "warnings": warnings,
            "flow_definitions_read": False,
            "connection_details_read": False,
            "secrets_returned": False,
            "cloud_resources_modified": False,
        }

    detect_failures = detect
    analyze = detect


class InactiveResourceDetector:
    """Read-only detector for inactive Azure resources and Power Automate flows."""

    def __init__(self, *, inactive_days: int = 30, now: datetime | None = None) -> None:
        self.inactive_days = inactive_days
        self.now = now

    def detect(
        self,
        items: Any = None,
        *,
        resources: Any = None,
        flows: Any = None,
        function_apps: Any = None,
        inactive_days: int | None = None,
        now: datetime | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        threshold_days = self.inactive_days if inactive_days is None else inactive_days
        current_time = now or self.now or datetime.now(timezone.utc)
        cutoff = current_time - timedelta(days=threshold_days)
        all_items: list[tuple[str, Any]] = []
        for label, value in (("resource", resources), ("flow", flows), ("function_app", function_apps)):
            for item in _as_list(value if value is not None else (items if label == "resource" else None)):
                all_items.append((label, item))
        if not all_items and items is not None:
            for item in _as_list(items):
                all_items.append(("resource", item))

        inactive: list[dict[str, Any]] = []
        for item_type, record in all_items:
            if not isinstance(record, Mapping):
                continue
            modified = _parse_time(
                _first(record, ("modified_on", "last_modified", "lastModifiedTime", "modifiedOn", "lastModified", "modified"))
            )
            state = str(_first(record, ("state", "status")) or "").strip().casefold()
            is_inactive = False
            reasons: list[str] = []
            if state in _INACTIVE_FLOW_STATES or state in {"stopped", "disabled", "deallocated"}:
                is_inactive = True
                reasons.append(f"state is {state}")
            if modified is not None and modified < cutoff:
                is_inactive = True
                reasons.append(f"not modified since {modified.isoformat()}")
            if modified is None and state not in {"running", "started", "available", "ready", "enabled", "active"} and state:
                # Conservative: only flag when an inactive state is already reported.
                pass
            if is_inactive:
                inactive.append(
                    {
                        "type": item_type,
                        "name": _name_of(record),
                        "id": _first(record, ("id", "resource_id", "flow_id")),
                        "last_modified": modified.isoformat() if modified else None,
                        "status": state or "Unknown",
                        "reasons": reasons,
                    }
                )
        return {
            "success": True,
            "operation": "inactive_resource_detection",
            "inactive_days": threshold_days,
            "checked_count": len(all_items),
            "inactive_count": len(inactive),
            "inactive": inactive,
            "cloud_resources_modified": False,
            "secrets_returned": False,
        }

    detect_inactive = detect
    find_inactive = detect


# Backwards/alternative names that callers or tests may use.
AzureResourceHealthMonitor = AzureResourceHealthChecker
FunctionAppAvailabilityMonitor = FunctionAppAvailabilityChecker
FunctionAppAvailability = FunctionAppAvailabilityChecker
AzureHealthChecker = AzureResourceHealthChecker
InactiveResourcesDetector = InactiveResourceDetector


def _json_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
