"""MCP tool implementations for the v1.1 unified cloud intelligence services.

These are read-only adapters over the MSAL identity authority and the Azure /
Power Platform discovery services. They keep MCP schemas small (strings and
lists only) and never return tokens or raw Microsoft error bodies.

Tests inject fakes through ``configure_unified_cloud_services`` so no live
Microsoft tenant, network or credentials are needed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from skyfall_cloud.azure_discovery import AzureDiscoveryService
from skyfall_cloud.azure_graph_inventory import AzureResourceInventory
from skyfall_cloud.cloud_governance import CloudGovernanceService
from skyfall_cloud.cloud_monitoring import CloudMonitoringService
from skyfall_cloud.cloud_orchestration import CloudOrchestrationService
from skyfall_cloud.cloud_reporting import CloudReportingService
from skyfall_cloud.controlled_operations import (
    ControlledOperationsService,
    OperationRequest,
)
from skyfall_cloud.copilot_intents import CopilotIntentRouter
from skyfall_cloud.cross_platform_intelligence import CrossPlatformIntelligence
from skyfall_cloud.msal_identity import UnifiedIdentityAuthority
from skyfall_cloud.powerplatform_catalog import PowerPlatformCatalog
from skyfall_cloud.powerplatform_discovery import PowerPlatformDiscovery
from skyfall_cloud.universal_execution import (
    ExecutionRequest,
    UniversalExecutionEngine,
    redact_public_text,
)
from skyfall_workspace.manager import WorkspaceManager

_SERVICES: dict[str, Any] = {}


def configure_unified_cloud_services(**services: Any) -> None:
    """Test seam: replace one or more lazily constructed services."""
    _SERVICES.clear()
    _SERVICES.update(services)


def _lazy(key: str, factory: Callable[[], Any]) -> Any:
    """Return a lazily built service, honouring injected test doubles."""
    service = _SERVICES.get(key)
    if service is None:
        service = factory()
        _SERVICES[key] = service
    return service


def _identity() -> UnifiedIdentityAuthority:
    """Return the shared MSAL identity authority."""
    return _lazy("identity", UnifiedIdentityAuthority)


def _azure_discovery() -> AzureDiscoveryService:
    """Return Azure discovery bound to the shared identity authority."""
    return _lazy("azure_discovery", lambda: AzureDiscoveryService(_identity()))


def _azure_inventory() -> AzureResourceInventory:
    """Return Azure inventory bound to the shared identity authority."""
    return _lazy(
        "azure_inventory",
        lambda: AzureResourceInventory(_identity()),
    )


def _powerplatform_discovery() -> PowerPlatformDiscovery:
    (
        "Return Power Platform discovery bound to the shared identity "
        "authority."
    )
    return _lazy(
        "powerplatform_discovery",
        lambda: PowerPlatformDiscovery(_identity()),
    )


def _catalog() -> Any:
    """Return the Power Platform catalog service."""
    return _lazy(
        "powerplatform_catalog",
        lambda: PowerPlatformCatalog(
            _identity(),
            http_client=getattr(_powerplatform_discovery(), "http", None),
        ),
    )


def _orchestration() -> Any:
    """Return the read-only cloud orchestration service."""
    return _lazy("orchestration", CloudOrchestrationService)


def _cross_platform() -> Any:
    """Return the cross-platform correlation service."""
    return _lazy("cross_platform", CrossPlatformIntelligence)


def _monitoring() -> Any:
    """Return the cloud monitoring service."""
    return _lazy("monitoring", CloudMonitoringService)


def _reporting() -> Any:
    """Return the cloud reporting service."""
    return _lazy("reporting", CloudReportingService)


def _governance() -> Any:
    """Return the cloud governance service."""
    return _lazy("governance", CloudGovernanceService)


def _operations() -> Any:
    """Return the controlled operations service."""
    return _lazy("operations", ControlledOperationsService)


def _copilot() -> Any:
    """Return the deterministic Copilot intent router."""
    return _lazy("copilot", CopilotIntentRouter)


def _engine() -> Any:
    """Return the plan-only execution engine with workspace fallback."""
    return _lazy(
        "engine",
        lambda: UniversalExecutionEngine(workspace_manager=WorkspaceManager()),
    )


def _render(payload: Any) -> str:
    """Render a tool payload as stable, readable JSON."""
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def _failure(exc: Exception) -> str:
    """Render a safe failure without echoing raw exception text."""
    error = f"Operation failed ({type(exc).__name__})."
    return _render({"success": False, "error": error})


def get_unified_identity_health() -> str:
    """Report secret-free health for all registered MSAL identity profiles."""
    try:
        return _render(_identity().overall_health())
    except Exception as exc:
        return _failure(exc)


def discover_azure_footprint(profile_id: str = "") -> str:
    (
        "Discover Azure tenants, subscriptions and management groups for one "
        "MSAL Azure profile."
    )
    try:
        return _render(
            _azure_discovery().tenant_subscription_overview(
                profile_id or None
            )
        )
    except Exception as exc:
        return _failure(exc)


def inventory_azure_resources(
    subscription_ids: list[str],
    categories: str = "",
) -> str:
    (
        "Inventory spec-defined Azure resource categories across explicit "
        "subscription IDs."
    )
    try:
        selected = (
            [item.strip() for item in categories.split(",") if item.strip()]
            or None
        )
        return _render(
            _azure_inventory().inventory(
                list(subscription_ids), categories=selected
            )
        )
    except Exception as exc:
        return _failure(exc)


def discover_powerplatform_environments(profile_id: str = "") -> str:
    (
        "Discover Power Platform environments for one independent MSAL "
        "profile."
    )
    try:
        return _render(
            _powerplatform_discovery().list_environments(profile_id or None)
        )
    except Exception as exc:
        return _failure(exc)


def describe_powerplatform_environment(environment_id: str) -> str:
    (
        "Inspect one explicitly selected environment's metadata, security "
        "flags and capacity."
    )
    try:
        return _render(
            _powerplatform_discovery().get_environment(environment_id)
        )
    except Exception as exc:
        return _failure(exc)


def _parse_json(value: str, default: Any) -> Any:
    """Parse bounded JSON input, returning a safe default on failure."""
    if not value:
        return default
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return default
    return parsed if isinstance(parsed, (list, dict)) else default


def inspect_powerplatform_catalog(
    environment_id: str, profile_id: str = ""
) -> str:
    (
        "Inventory flows, apps and connections for one selected environment "
        "(metadata only)."
    )
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
        subs = [
            item.strip()
            for item in subscription_ids.split(",")
            if item.strip()
        ]
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
    (
        "Correlate supplied Azure and Power Platform inventory JSON into "
        "dependencies and gaps."
    )
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
    (
        "Detect inactive/stale resources, anomalies and duplicates from "
        "supplied JSON."
    )
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
    (
        "Build a secret-safe executive report from supplied cloud inventory "
        "JSON."
    )
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
    (
        "Map a natural-language request to a read-only capability without "
        "executing it."
    )
    try:
        return _render(_copilot().route(utterance))
    except Exception as exc:
        return _failure(exc)


def build_operation_plan(
    operation: str,
    provider: str,
    target: str,
    profile_id: str = "",
) -> str:
    (
        "Build and policy-evaluate an operation plan. Never executes; "
        "mutating plans need approval."
    )
    try:
        service = _operations()
        request = OperationRequest(
            operation, provider, target, profile_id or None
        )
        plan = service.build_plan(request)
        safe_request = {
            key: redact_public_text(value) if isinstance(value, str) else value
            for key, value in dict(plan.get("request") or {}).items()
        }
        safe_plan = {
            "plan_id": plan.get("plan_id"),
            "request": safe_request,
            "risk": plan.get("risk"),
            "steps": list(plan.get("steps") or []),
            "execution_permitted": bool(plan.get("execution_permitted")),
            "approved": bool(plan.get("approved")),
            "approval_token": None,
            "token_material_returned": False,
        }
        return _render({
            "plan": safe_plan,
            "policy": service.describe_policy(),
            "token_material_returned": False,
        })
    except Exception as exc:
        return _failure(exc)


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
    (
        "Resolve and dry-run plan/simulate a capability request. Never starts "
        "processes."
    )
    try:
        engine = _engine()
        request = ExecutionRequest(
            operation=operation or "",
            tool_name=tool_name or "",
            capability_id=capability_id or "",
            provider=provider or "",
            target=target or "",
            profile_id=profile_id or None,
            workspace_id=workspace_id or None,
            file_id=file_id or None,
            query=query or None,
            allow_workspace_fallback=bool(allow_workspace_fallback),
            requires_mutation=bool(requires_mutation),
        )
        resolution, plan, record = engine.plan(request)
        simulation = None
        if plan.status.value == "planned" and not plan.mutable:
            result, sim_record = engine.simulate(plan)
            record = sim_record
            simulation = result.to_dict()
        payload = {
            "success": resolution.resolved,
            "plan_only": True,
            "executed": False,
            "process_started": False,
            "resolution": resolution.to_dict(),
            "plan": plan.to_dict(),
            "simulation": simulation,
            "record_id": record.record_id,
            "message": redact_public_text(
                "Resolved and planned in dry-run mode. No process was started."
                if resolution.resolved
                else "Request could not be resolved. No process was started."
            ),
        }
        return _render(payload)
    except Exception as exc:
        return _failure(exc)


def get_execution_history(record_id: str = "", limit: int = 20) -> str:
    (
        "Return bounded, redacted execution planning/simulation history. "
        "Never starts processes."
    )
    try:
        engine = _engine()
        bounded_limit = max(1, min(int(limit or 20), 50))
        if record_id:
            record = engine.get_record(record_id)
            records = [record] if record is not None else []
        else:
            records = engine.list_history(limit=bounded_limit)
        payload = {
            "success": True,
            "plan_only": True,
            "executed": False,
            "process_started": False,
            "count": len(records),
            "records": [record.to_dict() for record in records],
            "message": (
                "Execution history is plan/simulation metadata only. "
                "No process was started."
            ),
        }
        return _render(payload)
    except Exception as exc:
        return _failure(exc)
