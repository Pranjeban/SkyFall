"""MCP tool implementations for the v1.1 unified cloud intelligence services.

These are read-only adapters over the MSAL identity authority and the Azure /
Power Platform discovery services. They keep MCP schemas small (strings and
lists only) and never return tokens or raw Microsoft error bodies.

Tests inject fakes through ``configure_unified_cloud_services`` so no live
Microsoft tenant, network or credentials are needed.
"""

from __future__ import annotations

import json
from typing import Any

from skyfall_cloud.azure_discovery import AzureDiscoveryService
from skyfall_cloud.azure_graph_inventory import AzureResourceInventory
from skyfall_cloud.cloud_governance import CloudGovernanceService
from skyfall_cloud.cloud_monitoring import CloudMonitoringService
from skyfall_cloud.cloud_orchestration import CloudOrchestrationService
from skyfall_cloud.cloud_reporting import CloudReportingService
from skyfall_cloud.copilot_intents import CopilotIntentRouter
from skyfall_cloud.cross_platform_intelligence import CrossPlatformIntelligence
from skyfall_cloud.controlled_operations import ControlledOperationsService, OperationRequest
from skyfall_cloud.msal_identity import UnifiedIdentityAuthority
from skyfall_cloud.powerplatform_catalog import PowerPlatformCatalog
from skyfall_cloud.powerplatform_discovery import PowerPlatformDiscovery

_SERVICES: dict[str, Any] = {}


def configure_unified_cloud_services(**services: Any) -> None:
    """Test seam: replace one or more lazily constructed services."""
    _SERVICES.clear()
    _SERVICES.update(services)


def _identity() -> UnifiedIdentityAuthority:
    service = _SERVICES.get("identity")
    if service is None:
        service = UnifiedIdentityAuthority()
        _SERVICES["identity"] = service
    return service


def _azure_discovery() -> AzureDiscoveryService:
    service = _SERVICES.get("azure_discovery")
    if service is None:
        service = AzureDiscoveryService(_identity())
        _SERVICES["azure_discovery"] = service
    return service


def _azure_inventory() -> AzureResourceInventory:
    service = _SERVICES.get("azure_inventory")
    if service is None:
        service = AzureResourceInventory(_identity())
        _SERVICES["azure_inventory"] = service
    return service


def _powerplatform_discovery() -> PowerPlatformDiscovery:
    service = _SERVICES.get("powerplatform_discovery")
    if service is None:
        service = PowerPlatformDiscovery(_identity())
        _SERVICES["powerplatform_discovery"] = service
    return service


def _lazy(key: str, factory: Any) -> Any:
    service = _SERVICES.get(key)
    if service is None:
        service = factory()
        _SERVICES[key] = service
    return service


def _catalog() -> Any:
    return _lazy(
        "powerplatform_catalog",
        lambda: PowerPlatformCatalog(
            _identity(), http_client=getattr(_powerplatform_discovery(), "http", None)
        ),
    )


def _orchestration() -> Any:
    return _lazy("orchestration", CloudOrchestrationService)


def _cross_platform() -> Any:
    return _lazy("cross_platform", CrossPlatformIntelligence)


def _monitoring() -> Any:
    return _lazy("monitoring", CloudMonitoringService)


def _reporting() -> Any:
    return _lazy("reporting", CloudReportingService)


def _governance() -> Any:
    return _lazy("governance", CloudGovernanceService)


def _operations() -> Any:
    return _lazy("operations", ControlledOperationsService)


def _copilot() -> Any:
    return _lazy("copilot", CopilotIntentRouter)


def _render(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def _failure(exc: Exception) -> str:
    # Never render arbitrary exception text: it could echo a token/header.
    return _render({"success": False, "error": f"Operation failed ({type(exc).__name__})."})


def get_unified_identity_health() -> str:
    """Report secret-free health for all registered MSAL identity profiles."""
    try:
        return _render(_identity().overall_health())
    except Exception as exc:
        return _failure(exc)


def discover_azure_footprint(profile_id: str = "") -> str:
    """Discover Azure tenants, subscriptions and management groups for one MSAL Azure profile."""
    try:
        return _render(_azure_discovery().tenant_subscription_overview(profile_id or None))
    except Exception as exc:
        return _failure(exc)


def inventory_azure_resources(
    subscription_ids: list[str],
    categories: str = "",
) -> str:
    """Inventory spec-defined Azure resource categories across explicit subscription IDs."""
    try:
        selected = [item.strip() for item in categories.split(",") if item.strip()] or None
        return _render(
            _azure_inventory().inventory(list(subscription_ids), categories=selected)
        )
    except Exception as exc:
        return _failure(exc)


def discover_powerplatform_environments(profile_id: str = "") -> str:
    """Discover Power Platform environments for one independent MSAL profile."""
    try:
        return _render(_powerplatform_discovery().list_environments(profile_id or None))
    except Exception as exc:
        return _failure(exc)


def describe_powerplatform_environment(environment_id: str) -> str:
    """Inspect one explicitly selected environment's metadata, security flags and capacity."""
    try:
        return _render(_powerplatform_discovery().get_environment(environment_id))
    except Exception as exc:
        return _failure(exc)


def _parse_json(value: str, default: Any) -> Any:
    if not value:
        return default
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return default
    return parsed if isinstance(parsed, (list, dict)) else default


def inspect_powerplatform_catalog(environment_id: str, profile_id: str = "") -> str:
    """Inventory flows, apps and connections for one selected environment (metadata only)."""
    try:
        catalog = _catalog()
        selected = profile_id or None
        return _render({
            "success": True,
            "flows": catalog.list_flows(environment_id, selected),
            "apps": catalog.list_apps(environment_id, selected),
            "connections": catalog.list_connections(environment_id, selected),
            "token_material_returned": False,
        })
    except Exception as exc:
        return _failure(exc)


def run_cloud_orchestration(
    azure_profile_id: str = "",
    pp_profile_id: str = "",
    subscription_ids: str = "",
    environment_id: str = "",
) -> str:
    """Run a read-only correlated investigation across both cloud platforms."""
    try:
        subs = [item.strip() for item in subscription_ids.split(",") if item.strip()]
        return _render(_orchestration().run(
            azure_profile_id=azure_profile_id or None,
            pp_profile_id=pp_profile_id or None,
            subscription_ids=subs or None,
            environment_id=environment_id or None,
        ))
    except Exception as exc:
        return _failure(exc)


def correlate_cross_platform(
    azure_resources_json: str = "",
    pp_environments_json: str = "",
) -> str:
    """Correlate supplied Azure and Power Platform inventory JSON into dependencies and gaps."""
    try:
        engine = _cross_platform()
        azure = _parse_json(azure_resources_json, [])
        pp = _parse_json(pp_environments_json, [])
        return _render({
            "inventory": engine.unified_inventory(azure, pp),
            "dependencies": engine.map_dependencies(azure, pp),
            "gaps": engine.find_coverage_gaps(azure, pp),
        })
    except Exception as exc:
        return _failure(exc)


def cloud_health_report(
    azure_resources_json: str = "",
    pp_environments_json: str = "",
    pp_flows_json: str = "",
    pp_connections_json: str = "",
) -> str:
    """Detect inactive/stale resources, anomalies and duplicates from supplied JSON."""
    try:
        return _render(_monitoring().health_report(
            azure_resources=_parse_json(azure_resources_json, []),
            pp_environments=_parse_json(pp_environments_json, []),
            pp_flows=_parse_json(pp_flows_json, []),
            pp_connections=_parse_json(pp_connections_json, []),
        ))
    except Exception as exc:
        return _failure(exc)


def build_executive_report(
    azure_overview_json: str = "",
    pp_environments_json: str = "",
) -> str:
    """Build a secret-safe executive report from supplied cloud inventory JSON."""
    try:
        return _render(_reporting().build_executive_report(
            _parse_json(azure_overview_json, {}),
            _parse_json(pp_environments_json, []),
        ))
    except Exception as exc:
        return _failure(exc)


def governance_summary() -> str:
    """Report in-memory audit counts and the read-only policy boundary."""
    try:
        return _render({
            "summary": _governance().summary(),
            "policy": ControlledOperationsService.describe_policy(),
        })
    except Exception as exc:
        return _failure(exc)


def route_copilot_intent(utterance: str) -> str:
    """Map a natural-language request to a read-only capability without executing it."""
    try:
        return _render(_copilot().route(utterance))
    except Exception as exc:
        return _failure(exc)


def build_operation_plan(operation: str, provider: str, target: str, profile_id: str = "") -> str:
    """Build and policy-evaluate an operation plan. Never executes; mutating plans need approval."""
    try:
        service = _operations()
        request = OperationRequest(operation, provider, target, profile_id or None)
        plan = service.build_plan(request)
        return _render({
            "plan": plan,
            "policy": service.describe_policy(),
            "token_material_returned": False,
        })
    except Exception as exc:
        return _failure(exc)
