"""Read-only Azure Function App inventory via Azure Resource Graph.

The implementation obtains a short-lived ARM token from the selected Azure
CLI profile, queries Azure Resource Graph, and writes a local XLSX workbook.
It never reads app settings, connection strings, publishing profiles, host keys,
function keys, or any other secret-bearing configuration.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import ssl
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import httpx
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo

from .azure_profiles import AzureProfileManager
from .reporting import build_report_path


RESOURCE_GRAPH_ENDPOINT = (
    "https://management.azure.com/providers/Microsoft.ResourceGraph/resources"
    "?api-version=2022-10-01"
)
RESOURCE_GRAPH_PAGE_SIZE = 1000
MAX_RESOURCE_GRAPH_PAGES = 100

FUNCTION_APPS_QUERY = r"""
Resources
| where type =~ 'microsoft.web/sites'
| where tostring(kind) contains 'functionapp'
| project
    id,
    name,
    kind,
    location,
    resourceGroup,
    subscriptionId,
    tags,
    state = tostring(properties.state),
    defaultHostName = tostring(properties.defaultHostName),
    httpsOnly = tobool(properties.httpsOnly),
    publicNetworkAccess = tostring(properties.publicNetworkAccess),
    serverFarmId = tostring(properties.serverFarmId),
    linuxFxVersion = tostring(properties.siteConfig.linuxFxVersion),
    netFrameworkVersion = tostring(properties.siteConfig.netFrameworkVersion),
    nodeVersion = tostring(properties.siteConfig.nodeVersion),
    pythonVersion = tostring(properties.siteConfig.pythonVersion),
    powerShellVersion = tostring(properties.siteConfig.powerShellVersion),
    functionsExtensionVersion = tostring(properties.siteConfig.functionsExtensionVersion),
    alwaysOn = tobool(properties.siteConfig.alwaysOn),
    ftpsState = tostring(properties.siteConfig.ftpsState),
    minTlsVersion = tostring(properties.siteConfig.minTlsVersion),
    http20Enabled = tobool(properties.siteConfig.http20Enabled),
    functionAppScaleLimit = tostring(properties.siteConfig.functionAppScaleLimit),
    preWarmedInstanceCount = tostring(properties.siteConfig.preWarmedInstanceCount),
    virtualNetworkSubnetId = tostring(properties.virtualNetworkSubnetId),
    identityType = tostring(identity.type)
| order by id asc
""".strip()

HOSTING_PLANS_QUERY = r"""
Resources
| where type =~ 'microsoft.web/serverfarms'
| project
    id,
    planName = name,
    planKind = tostring(kind),
    planLocation = location,
    planSkuName = tostring(sku.name),
    planSkuTier = tostring(sku.tier),
    planSkuSize = tostring(sku.size),
    planReserved = tostring(properties.reserved),
    planMaximumElasticWorkerCount = tostring(properties.maximumElasticWorkerCount),
    planPerSiteScaling = tostring(properties.perSiteScaling),
    planNumberOfWorkers = tostring(properties.numberOfWorkers),
    planWorkerSize = tostring(properties.workerSize)
| order by id asc
""".strip()

_SECRET_TAG_KEY = re.compile(
    r"(?i)(secret|password|token|credential|connection.?string|sas|private.?key|access.?key)"
)
_TOKEN_LIKE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")


class AzureInventoryError(RuntimeError):
    """Raised when a complete, trustworthy inventory cannot be produced."""


class AzureFunctionAppInventory:
    """Create a read-only Function App inventory for selected Azure profiles."""

    def __init__(
        self,
        profile_manager: AzureProfileManager | None = None,
        *,
        project_root: str | Path | None = None,
        token_provider: Callable[[str], str] | None = None,
        http_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.profile_manager = profile_manager or AzureProfileManager()
        self.project_root = Path(
            project_root
            or os.environ.get("SKYFALL_ROOT")
            or Path(__file__).resolve().parents[1]
        ).resolve()
        self.token_provider = token_provider or self._get_arm_access_token
        self.http_client_factory = http_client_factory or self._create_http_client

    @staticmethod
    def _create_http_client() -> httpx.Client:
        # On Windows, create_default_context loads roots from the Windows
        # certificate stores, including organization-installed enterprise CAs.
        context = ssl.create_default_context()
        return httpx.Client(
            verify=context,
            timeout=httpx.Timeout(60.0, connect=20.0),
            follow_redirects=False,
        )

    def _profile_environment(self, profile_id: str) -> dict[str, str]:
        profile = self.profile_manager.store.get_profile(profile_id)
        if profile["profile_id"] == "azure-cli-default":
            return {}
        return {"AZURE_CONFIG_DIR": str(profile["config_dir"])}

    def _get_arm_access_token(self, profile_id: str) -> str:
        """Get a short-lived ARM token without returning/logging it elsewhere."""
        executable = shutil.which("az")
        if not executable:
            raise AzureInventoryError(
                "Azure CLI (az) was not found on PATH. Install or repair Azure CLI, then retry."
            )

        environment = os.environ.copy()
        environment.update(self._profile_environment(profile_id))
        try:
            completed = subprocess.run(
                [
                    executable,
                    "account",
                    "get-access-token",
                    "--resource",
                    "https://management.azure.com/",
                    "--output",
                    "json",
                    "--only-show-errors",
                ],
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                env=environment,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise AzureInventoryError("Azure CLI token acquisition timed out.") from exc
        except OSError as exc:
            raise AzureInventoryError(f"Could not start Azure CLI: {exc}") from exc

        if completed.returncode != 0:
            # Do not echo raw CLI output; it can contain tenant/user data.
            detail = (completed.stderr or completed.stdout or "").strip()
            if "az login" in detail.casefold() or "not logged" in detail.casefold():
                raise AzureInventoryError(
                    "This Azure profile is not authenticated. Ask SKYFALL to sign in to the selected profile first."
                )
            raise AzureInventoryError(
                "Azure CLI could not acquire an Azure Resource Manager token. "
                "Check this profile's sign-in and permissions."
            )

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise AzureInventoryError(
                "Azure CLI returned an unreadable token response."
            ) from exc
        token = payload.get("accessToken") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise AzureInventoryError("Azure CLI did not return an ARM access token.")
        # Token remains only in this method's caller memory and is never logged,
        # returned from the MCP tool, persisted, or placed in a report.
        return token

    @staticmethod
    def _safe_tags(tags: Any) -> dict[str, str]:
        if not isinstance(tags, dict):
            return {}
        safe: dict[str, str] = {}
        for key, value in tags.items():
            key_text = str(key)[:120]
            if _SECRET_TAG_KEY.search(key_text):
                safe[key_text] = "[REDACTED]"
                continue
            value_text = str(value)[:500]
            if _TOKEN_LIKE.search(value_text):
                value_text = _TOKEN_LIKE.sub("[REDACTED_TOKEN]", value_text)
            safe[key_text] = value_text
        return safe

    @staticmethod
    def _as_bool_text(value: Any) -> str:
        if value is True or str(value).casefold() == "true":
            return "Yes"
        if value is False or str(value).casefold() == "false":
            return "No"
        return ""

    @staticmethod
    def _runtime_stack(item: Mapping[str, Any]) -> str:
        linux_fx = str(item.get("linuxFxVersion") or "").strip()
        if linux_fx:
            return linux_fx
        for label, key in (
            (".NET", "netFrameworkVersion"),
            ("Node.js", "nodeVersion"),
            ("Python", "pythonVersion"),
            ("PowerShell", "powerShellVersion"),
        ):
            value = str(item.get(key) or "").strip()
            if value:
                return f"{label} {value}"
        return "Not reported by Resource Graph"

    @staticmethod
    def _os_type(item: Mapping[str, Any], plan: Mapping[str, Any] | None = None) -> str:
        kind = str(item.get("kind") or "").casefold()
        if "linux" in kind or str((plan or {}).get("planReserved", "")).casefold() == "true":
            return "Linux"
        if "windows" in kind:
            return "Windows"
        if (plan or {}).get("planKind"):
            plan_kind = str(plan.get("planKind", "")).casefold()
            if "linux" in plan_kind:
                return "Linux"
            if "windows" in plan_kind:
                return "Windows"
        return "Not reported"

    def _query_resource_graph(
        self,
        client: httpx.Client,
        token: str,
        subscription_ids: list[str],
        query: str,
    ) -> list[dict[str, Any]]:
        if not subscription_ids:
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        options: dict[str, Any] = {"$top": RESOURCE_GRAPH_PAGE_SIZE}
        results: list[dict[str, Any]] = []
        seen_tokens: set[str] = set()

        for _page in range(MAX_RESOURCE_GRAPH_PAGES):
            body: dict[str, Any] = {
                "subscriptions": subscription_ids,
                "query": query,
                "options": dict(options),
            }
            try:
                response = client.post(RESOURCE_GRAPH_ENDPOINT, headers=headers, json=body)
            except httpx.TimeoutException as exc:
                raise AzureInventoryError("Azure Resource Graph request timed out.") from exc
            except httpx.HTTPError as exc:
                raise AzureInventoryError(
                    "Could not reach Azure Resource Graph. Check network, proxy and certificate trust."
                ) from exc

            if response.status_code in (401, 403):
                raise AzureInventoryError(
                    "Azure Resource Graph access was denied. Verify the account has Reader access "
                    "and the Resource Graph query permission on the selected subscriptions."
                )
            if response.status_code == 429:
                raise AzureInventoryError(
                    "Azure Resource Graph throttled this inventory request. Wait briefly and retry."
                )
            if response.status_code < 200 or response.status_code >= 300:
                raise AzureInventoryError(
                    f"Azure Resource Graph returned HTTP {response.status_code}. "
                    "The inventory was not marked complete."
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise AzureInventoryError("Azure Resource Graph returned invalid JSON.") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("data", []), list):
                raise AzureInventoryError("Azure Resource Graph returned an unexpected response shape.")

            page_rows = payload.get("data", [])
            results.extend(row for row in page_rows if isinstance(row, dict))
            skip_token = payload.get("$skipToken") or payload.get("skipToken")
            truncated = str(payload.get("resultTruncated", "false")).casefold() == "true"
            if skip_token:
                token_text = str(skip_token)
                if token_text in seen_tokens:
                    raise AzureInventoryError("Azure Resource Graph returned a repeated pagination token.")
                seen_tokens.add(token_text)
                options = {"$skipToken": token_text}
                continue
            if truncated:
                raise AzureInventoryError(
                    "Azure Resource Graph truncated the result without a continuation token. "
                    "SKYFALL cannot guarantee a complete inventory, so no success report was produced."
                )
            return results

        raise AzureInventoryError(
            f"Azure Resource Graph exceeded the safety limit of {MAX_RESOURCE_GRAPH_PAGES} pages."
        )

    def _profiles_to_process(self, profile_id: str) -> list[dict[str, Any]]:
        selected = (profile_id or "all").strip()
        if selected.casefold() in {"all", "*"}:
            return self.profile_manager.store.list_profiles()
        return [self.profile_manager.store.get_profile(selected)]

    def inventory(
        self,
        *,
        profile_id: str = "all",
        subscription_ids: Iterable[str] | None = None,
        generate_excel: bool = True,
    ) -> dict[str, Any]:
        """Inventory Function Apps across selected authenticated profiles.

        `subscription_ids`, when supplied, is an allow-filter: every ID must
        already be visible in the selected authenticated Azure CLI profiles.
        """
        if os.environ.get("SKYFALL_TEST_MODE") == "1":
            return {
                "success": False,
                "status": "blocked_test_mode",
                "error": "External Azure Resource Graph access is disabled in SKYFALL_TEST_MODE.",
                "cloud_resources_modified": False,
                "secrets_returned": False,
            }

        requested_ids = [str(value).strip() for value in (subscription_ids or []) if str(value).strip()]
        if len(requested_ids) != len(set(value.casefold() for value in requested_ids)):
            raise ValueError("subscription_ids contains duplicate values.")

        profiles = self._profiles_to_process(profile_id)
        if not profiles:
            return {
                "success": False,
                "status": "failed",
                "error": "No Azure profiles are configured in SKYFALL.",
                "cloud_resources_modified": False,
                "secrets_returned": False,
            }

        all_apps: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        discovered_subscriptions: dict[str, dict[str, str]] = {}
        successful_profiles: list[str] = []
        requested_ids_found: set[str] = set()

        for profile in profiles:
            current_profile_id = str(profile["profile_id"])
            profile_name = str(profile["name"])
            auth = self.profile_manager.get_auth_status(current_profile_id)
            if not auth.get("authenticated"):
                errors.append({
                    "profile": profile_name,
                    "profile_id": current_profile_id,
                    "stage": "authentication",
                    "error": "Profile is not authenticated; sign in to this profile before inventory.",
                })
                continue

            subscription_result = self.profile_manager.list_subscriptions(
                current_profile_id, refresh=True
            )
            if not subscription_result.get("success"):
                errors.append({
                    "profile": profile_name,
                    "profile_id": current_profile_id,
                    "stage": "subscriptions",
                    "error": str(subscription_result.get("error") or "Subscription discovery failed."),
                })
                continue

            subscriptions = [
                item for item in subscription_result.get("subscriptions", [])
                if str(item.get("state", "")).casefold() == "enabled"
            ]
            visible_ids = {str(item.get("subscription_id", "")).casefold() for item in subscriptions}
            if requested_ids:
                matching_subscriptions = [
                    item for item in subscriptions
                    if str(item.get("subscription_id", "")).casefold()
                    in {value.casefold() for value in requested_ids}
                ]
                if not matching_subscriptions:
                    # A targeted subscription may belong to one of several
                    # connected profiles. Its absence from another profile is
                    # expected and is not treated as a discovery failure.
                    continue
                requested_ids_found.update(
                    str(item.get("subscription_id", "")).casefold()
                    for item in matching_subscriptions
                )
                subscriptions = matching_subscriptions

            if not subscriptions:
                errors.append({
                    "profile": profile_name,
                    "profile_id": current_profile_id,
                    "stage": "subscriptions",
                    "error": "No enabled accessible subscriptions were found for this profile.",
                })
                continue

            subscription_id_list = [str(item["subscription_id"]) for item in subscriptions]
            for item in subscriptions:
                sub_id = str(item.get("subscription_id", ""))
                discovered_subscriptions[f"{current_profile_id}:{sub_id}".casefold()] = {
                    "profile_id": current_profile_id,
                    "profile": profile_name,
                    "subscription_id": sub_id,
                    "subscription_name": str(item.get("name", "")),
                    "tenant_id": str(item.get("tenant_id", "")),
                    "state": str(item.get("state", "")),
                }

            try:
                arm_token = self.token_provider(current_profile_id)
                with self.http_client_factory() as client:
                    apps = self._query_resource_graph(
                        client, arm_token, subscription_id_list, FUNCTION_APPS_QUERY
                    )
                    try:
                        plans = self._query_resource_graph(
                            client, arm_token, subscription_id_list, HOSTING_PLANS_QUERY
                        )
                    except Exception as plan_exc:
                        # Hosting-plan lookup enriches the inventory, but a plan
                        # lookup failure must not discard successfully discovered
                        # Function Apps. Mark the result partial instead.
                        plans = []
                        errors.append({
                            "profile": profile_name,
                            "profile_id": current_profile_id,
                            "stage": "hosting_plans",
                            "error": f"{type(plan_exc).__name__}: {str(plan_exc)[:500]}",
                        })
                plan_map = {
                    str(plan.get("id", "")).casefold(): plan
                    for plan in plans if plan.get("id")
                }
                sub_map = {
                    str(item.get("subscription_id", "")).casefold(): item
                    for item in subscriptions
                }
                for app in apps:
                    sub = sub_map.get(str(app.get("subscriptionId", "")).casefold(), {})
                    plan = plan_map.get(str(app.get("serverFarmId", "")).casefold(), {})
                    safe_tags = self._safe_tags(app.get("tags"))
                    app_record = {
                        "profile_id": current_profile_id,
                        "profile": profile_name,
                        "subscription_id": str(app.get("subscriptionId", "") or sub.get("subscription_id", "")),
                        "subscription_name": str(sub.get("name", "")),
                        "tenant_id": str(sub.get("tenant_id", "")),
                        "resource_group": str(app.get("resourceGroup", "")),
                        "name": str(app.get("name", "")),
                        "resource_id": str(app.get("id", "")),
                        "kind": str(app.get("kind", "")),
                        "region": str(app.get("location", "")),
                        "state": str(app.get("state", "")),
                        "default_hostname": str(app.get("defaultHostName", "")),
                        "https_only": self._as_bool_text(app.get("httpsOnly")),
                        "public_network_access": str(app.get("publicNetworkAccess", "")),
                        "os_type": self._os_type(app, plan),
                        "runtime_stack": self._runtime_stack(app),
                        "functions_runtime_version": str(app.get("functionsExtensionVersion", "")),
                        "linux_fx_version": str(app.get("linuxFxVersion", "")),
                        "net_framework_version": str(app.get("netFrameworkVersion", "")),
                        "node_version": str(app.get("nodeVersion", "")),
                        "python_version": str(app.get("pythonVersion", "")),
                        "powershell_version": str(app.get("powerShellVersion", "")),
                        "always_on": self._as_bool_text(app.get("alwaysOn")),
                        "ftps_state": str(app.get("ftpsState", "")),
                        "minimum_tls_version": str(app.get("minTlsVersion", "")),
                        "http2_enabled": self._as_bool_text(app.get("http20Enabled")),
                        "function_app_scale_limit": str(app.get("functionAppScaleLimit", "")),
                        "prewarmed_instance_count": str(app.get("preWarmedInstanceCount", "")),
                        "vnet_subnet_id": str(app.get("virtualNetworkSubnetId", "")),
                        "managed_identity_type": str(app.get("identityType", "")),
                        "hosting_plan_id": str(app.get("serverFarmId", "")),
                        "hosting_plan_name": str(plan.get("planName", "")),
                        "hosting_plan_kind": str(plan.get("planKind", "")),
                        "hosting_plan_region": str(plan.get("planLocation", "")),
                        "hosting_plan_sku": str(plan.get("planSkuName", "")),
                        "hosting_plan_tier": str(plan.get("planSkuTier", "")),
                        "hosting_plan_size": str(plan.get("planSkuSize", "")),
                        "hosting_plan_os_reserved": str(plan.get("planReserved", "")),
                        "hosting_plan_max_elastic_workers": str(plan.get("planMaximumElasticWorkerCount", "")),
                        "hosting_plan_per_site_scaling": str(plan.get("planPerSiteScaling", "")),
                        "hosting_plan_number_of_workers": str(plan.get("planNumberOfWorkers", "")),
                        "hosting_plan_worker_size": str(plan.get("planWorkerSize", "")),
                        "tags": safe_tags,
                    }
                    # Avoid including resource records with malformed IDs/names.
                    if app_record["name"] and app_record["resource_id"]:
                        all_apps.append(app_record)
                successful_profiles.append(profile_name)
            except Exception as exc:
                errors.append({
                    "profile": profile_name,
                    "profile_id": current_profile_id,
                    "stage": "resource_graph",
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                })

        if requested_ids:
            missing_requested = [
                value for value in requested_ids
                if value.casefold() not in requested_ids_found
            ]
            if missing_requested:
                errors.append({
                    "profile": "selected scope",
                    "profile_id": str(profile_id or "all"),
                    "stage": "subscription_filter",
                    "error": "Requested subscription IDs were not enabled or not visible in any authenticated selected profile (or were not found): "
                    + ", ".join(missing_requested),
                })

        # Deduplicate subscriptions exposed by multiple profiles while retaining
        # profile provenance on each resource record.
        deduped_apps: dict[str, dict[str, Any]] = {}
        for record in all_apps:
            key = f"{record['subscription_id']}:{record['resource_id']}".casefold()
            if key not in deduped_apps:
                record["profiles"] = [record["profile"]]
                deduped_apps[key] = record
            else:
                existing = deduped_apps[key]
                profiles_for_resource = set(existing.get("profiles", []))
                profiles_for_resource.add(record["profile"])
                existing["profiles"] = sorted(profiles_for_resource)
                existing["profile"] = "; ".join(existing["profiles"])

        function_apps = sorted(
            deduped_apps.values(),
            key=lambda item: (
                item.get("subscription_name", "").casefold(),
                item.get("resource_group", "").casefold(),
                item.get("name", "").casefold(),
            ),
        )
        subscription_rows = list(discovered_subscriptions.values())
        if not successful_profiles and not function_apps:
            return {
                "success": False,
                "status": "failed",
                "profile_count": len(profiles),
                "subscription_count": len(subscription_rows),
                "function_app_count": 0,
                "errors": errors,
                "error": "No authenticated Azure profile completed Function App discovery. Review the account and permission errors.",
                "cloud_resources_modified": False,
                "secrets_returned": False,
            }

        report_path: str | None = None
        sheets: list[str] = []
        if generate_excel:
            if requested_ids and len(subscription_rows) == 1:
                scope_label = subscription_rows[0].get("subscription_name") or "Selected-Subscription"
            elif requested_ids:
                scope_label = "Selected-Subscriptions"
            else:
                scope_label = "All-Subscriptions"
            report_path, sheets = self._write_excel_report(
                function_apps=function_apps,
                subscriptions=subscription_rows,
                errors=errors,
                profile_count=len(successful_profiles),
                scope_label=scope_label,
            )

        status = "partial" if errors else "success"
        return {
            "success": True,
            "status": status,
            "operation": "azure_function_app_inventory",
            "profile_count": len(successful_profiles),
            "subscription_count": len({row["subscription_id"] for row in subscription_rows}),
            "function_app_count": len(function_apps),
            "hosting_plan_count": len({row["hosting_plan_id"] for row in function_apps if row.get("hosting_plan_id")}),
            "regions": sorted({row["region"] for row in function_apps if row.get("region")}),
            "errors": errors,
            "report": {
                "format": "xlsx" if generate_excel else None,
                "path": report_path,
                "worksheets": sheets,
            } if generate_excel else None,
            "preview": [
                {
                    "name": row["name"],
                    "subscription": row["subscription_name"],
                    "resource_group": row["resource_group"],
                    "region": row["region"],
                    "state": row["state"],
                    "runtime": row["runtime_stack"],
                    "hosting_plan_sku": row["hosting_plan_sku"],
                    "profiles": row["profile"],
                }
                for row in function_apps[:10]
            ],
            "scope": "all_enabled_subscriptions_visible_to_selected_registered_azure_profile_or_profiles",
            "data_source": "Azure Resource Graph REST API",
            "resource_graph_api_version": "2022-10-01",
            "cloud_resources_modified": False,
            "secrets_returned": False,
            "sensitive_app_settings_read": False,
            "note": (
                "Inventory includes indexed resource and non-secret configuration metadata. "
                "Azure Resource Graph can lag recent changes. App settings, connection strings, "
                "publishing profiles, host keys and function keys are intentionally excluded."
            ),
        }

    def _write_excel_report(
        self,
        *,
        function_apps: list[dict[str, Any]],
        subscriptions: list[dict[str, Any]],
        errors: list[dict[str, str]],
        profile_count: int,
        scope_label: str = "All-Subscriptions",
    ) -> tuple[str, list[str]]:
        report_dir = self.project_root / "reports" / "Azure"
        output_path = build_report_path(
            report_dir, ["Azure-Function-Apps", scope_label]
        )
        temp_path = output_path.with_name(output_path.stem + ".tmp.xlsx")

        workbook = Workbook()
        summary = workbook.active
        summary.title = "Summary"
        summary.append(["SKYFALL - Azure Function App Inventory"])
        summary.append(["Generated (UTC)", datetime.now(timezone.utc).isoformat(timespec="seconds")])
        summary.append(["Authenticated Azure profiles", profile_count])
        summary.append(["Accessible subscriptions queried", len({s.get('subscription_id') for s in subscriptions})])
        summary.append(["Function Apps discovered", len(function_apps)])
        summary.append(["Hosting plans referenced", len({r.get('hosting_plan_id') for r in function_apps if r.get('hosting_plan_id')})])
        summary.append(["Discovery errors / partial scopes", len(errors)])
        summary.append(["Cloud changes performed", "No - read-only inventory"])
        summary.append(["Secrets or app settings retrieved", "No"])
        summary.append(["Data source", "Azure Resource Graph REST API"])
        summary.append(["Completeness note", "Azure Resource Graph indexing may lag recent resource changes."])
        summary.append([])
        summary.append(["Function Apps by region", "Count"])
        region_counts = Counter(row.get("region", "Unknown") or "Unknown" for row in function_apps)
        for region, count in sorted(region_counts.items()):
            summary.append([region, count])
        summary.append([])
        summary.append(["Function Apps by state", "Count"])
        state_counts = Counter(row.get("state", "Unknown") or "Unknown" for row in function_apps)
        for state, count in sorted(state_counts.items()):
            summary.append([state, count])

        function_columns = [
            ("Account profile(s)", "profile"),
            ("Subscription", "subscription_name"),
            ("Subscription ID", "subscription_id"),
            ("Tenant ID", "tenant_id"),
            ("Resource Group", "resource_group"),
            ("Function App", "name"),
            ("Kind", "kind"),
            ("Region", "region"),
            ("State", "state"),
            ("OS", "os_type"),
            ("Runtime Stack", "runtime_stack"),
            ("Functions Runtime Version", "functions_runtime_version"),
            ("Hosting Plan", "hosting_plan_name"),
            ("Plan SKU", "hosting_plan_sku"),
            ("Plan Tier", "hosting_plan_tier"),
            ("Plan Size", "hosting_plan_size"),
            ("HTTPS Only", "https_only"),
            ("Public Network Access", "public_network_access"),
            ("Always On", "always_on"),
            ("FTPS State", "ftps_state"),
            ("Minimum TLS", "minimum_tls_version"),
            ("HTTP/2 Enabled", "http2_enabled"),
            ("VNet Subnet ID", "vnet_subnet_id"),
            ("Managed Identity Type", "managed_identity_type"),
            ("Default Hostname", "default_hostname"),
            ("Resource ID", "resource_id"),
        ]
        apps_sheet = workbook.create_sheet("Function Apps")
        self._append_table(apps_sheet, function_columns, function_apps, "FunctionAppsTable")

        plan_columns = [
            ("Hosting Plan", "hosting_plan_name"),
            ("Plan ID", "hosting_plan_id"),
            ("SKU", "hosting_plan_sku"),
            ("Tier", "hosting_plan_tier"),
            ("Size", "hosting_plan_size"),
            ("Kind", "hosting_plan_kind"),
            ("Region", "hosting_plan_region"),
            ("Reserved (Linux)", "hosting_plan_os_reserved"),
            ("Maximum Elastic Workers", "hosting_plan_max_elastic_workers"),
            ("Per-site Scaling", "hosting_plan_per_site_scaling"),
            ("Number of Workers", "hosting_plan_number_of_workers"),
            ("Worker Size", "hosting_plan_worker_size"),
        ]
        unique_plans: dict[str, dict[str, Any]] = {}
        for row in function_apps:
            plan_id = str(row.get("hosting_plan_id") or "")
            if plan_id:
                unique_plans.setdefault(plan_id.casefold(), row)
        plans_sheet = workbook.create_sheet("Hosting Plans")
        self._append_table(plans_sheet, plan_columns, list(unique_plans.values()), "HostingPlansTable")

        config_columns = [
            ("Function App", "name"),
            ("Subscription", "subscription_name"),
            ("Resource Group", "resource_group"),
            ("Runtime Stack", "runtime_stack"),
            ("Linux FX Version", "linux_fx_version"),
            (".NET Version", "net_framework_version"),
            ("Node Version", "node_version"),
            ("Python Version", "python_version"),
            ("PowerShell Version", "powershell_version"),
            ("Functions Runtime", "functions_runtime_version"),
            ("Scale Limit", "function_app_scale_limit"),
            ("Prewarmed Instances", "prewarmed_instance_count"),
            ("Always On", "always_on"),
            ("FTPS State", "ftps_state"),
            ("Minimum TLS", "minimum_tls_version"),
            ("HTTP/2", "http2_enabled"),
        ]
        config_sheet = workbook.create_sheet("Configuration")
        self._append_table(config_sheet, config_columns, function_apps, "FunctionAppConfigTable")

        network_columns = [
            ("Function App", "name"),
            ("Subscription", "subscription_name"),
            ("Resource Group", "resource_group"),
            ("HTTPS Only", "https_only"),
            ("Public Network Access", "public_network_access"),
            ("VNet Subnet ID", "vnet_subnet_id"),
            ("Managed Identity Type", "managed_identity_type"),
            ("Default Hostname", "default_hostname"),
        ]
        network_sheet = workbook.create_sheet("Networking")
        self._append_table(network_sheet, network_columns, function_apps, "FunctionAppNetworkTable")

        tags_sheet = workbook.create_sheet("Tags")
        tag_rows: list[dict[str, Any]] = []
        for row in function_apps:
            for key, value in sorted((row.get("tags") or {}).items()):
                tag_rows.append({
                    "function_app": row.get("name"),
                    "subscription": row.get("subscription_name"),
                    "resource_group": row.get("resource_group"),
                    "tag_key": key,
                    "tag_value": value,
                })
        self._append_table(
            tags_sheet,
            [("Function App", "function_app"), ("Subscription", "subscription"),
             ("Resource Group", "resource_group"), ("Tag Key", "tag_key"), ("Tag Value", "tag_value")],
            tag_rows,
            "FunctionAppTagsTable",
        )

        errors_sheet = workbook.create_sheet("Discovery Errors")
        self._append_table(
            errors_sheet,
            [("Profile", "profile"), ("Profile ID", "profile_id"), ("Stage", "stage"), ("Error", "error")],
            errors,
            "DiscoveryErrorsTable",
        )

        # Cloud resource names, tags and error messages are external data.
        # Escape formula-like strings before writing the workbook so a resource
        # tag cannot become an Excel formula when an engineer opens the report.
        self._sanitize_workbook_text_cells(workbook)

        for sheet in workbook.worksheets:
            sheet.sheet_view.showGridLines = False
            sheet.freeze_panes = "A2" if sheet.title != "Summary" else "A2"
            for cell in sheet[1]:
                cell.font = Font(name="Aptos Display", bold=True, color="FFFFFF", size=12)
                cell.fill = PatternFill("solid", fgColor="183A63")
                cell.alignment = Alignment(vertical="center", wrap_text=True)
            sheet.row_dimensions[1].height = 28
            for column_cells in sheet.columns:
                column_letter = column_cells[0].column_letter
                max_width = 12
                for cell in column_cells[:250]:
                    value = "" if cell.value is None else str(cell.value)
                    max_width = max(max_width, min(len(value) + 2, 52))
                sheet.column_dimensions[column_letter].width = min(max_width, 52)

        try:
            workbook.save(temp_path)
            os.replace(temp_path, output_path)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

        return str(output_path), [sheet.title for sheet in workbook.worksheets]

    @staticmethod
    def _sanitize_workbook_text_cells(workbook: Workbook) -> None:
        """Force untrusted formula-like strings to remain literal Excel text."""
        formula_prefixes = ("=", "+", "-", "@")
        for worksheet in workbook.worksheets:
            for row in worksheet.iter_rows():
                for cell in row:
                    value = cell.value
                    if not isinstance(value, str):
                        continue
                    trimmed = value.lstrip(" \t\r\n")
                    if cell.data_type == "f" or trimmed.startswith(formula_prefixes):
                        cell.value = "'" + value

    @staticmethod
    def _append_table(
        worksheet: Any,
        columns: list[tuple[str, str]],
        rows: list[dict[str, Any]],
        table_name: str,
    ) -> None:
        worksheet.append([label for label, _key in columns])
        for record in rows:
            values: list[Any] = []
            for _label, key in columns:
                value = record.get(key, "")
                if isinstance(value, (dict, list, tuple)):
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                if value is None:
                    value = ""
                values.append(str(value) if isinstance(value, (dict, list, tuple)) else value)
            worksheet.append(values)

        # Excel tables require at least one data row. An empty inventory still
        # receives a header row and remains a valid workbook.
        if rows:
            end_column = worksheet.cell(row=1, column=len(columns)).column_letter
            ref = f"A1:{end_column}{len(rows) + 1}"
            table = Table(displayName=table_name, ref=ref)
            table.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium2",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False,
            )
            worksheet.add_table(table)


class AzureResourceInventory(AzureFunctionAppInventory):
    """Inventory general Azure resource metadata through the shared safe ARG path."""

    RESOURCE_QUERY = r"""
Resources
| project
    id,
    name,
    type,
    kind,
    location,
    resourceGroup,
    subscriptionId,
    tagsCount = array_length(bag_keys(tags)),
    provisioningState = tostring(properties.provisioningState),
    skuName = tostring(sku.name),
    skuTier = tostring(sku.tier),
    managedBy
| order by type asc, id asc
""".strip()

    @staticmethod
    def _normalize_resource_types(
        resource_type: Any = None,
        resource_types: Any = None,
        resource_type_filter: Any = None,
    ) -> list[str]:
        values: list[str] = []
        for candidate in (resource_type, resource_type_filter):
            if isinstance(candidate, str):
                values.extend(part.strip() for part in candidate.split(",") if part.strip())
            elif candidate is not None:
                values.append(str(candidate).strip())
        if isinstance(resource_types, (list, tuple, set)):
            for candidate in resource_types:
                if isinstance(candidate, str):
                    values.extend(part.strip() for part in candidate.split(",") if part.strip())
                elif candidate is not None:
                    values.append(str(candidate).strip())
        elif isinstance(resource_types, str):
            values.extend(part.strip() for part in resource_types.split(",") if part.strip())
        elif resource_types is not None:
            values.append(str(resource_types).strip())

        normalized: list[str] = []
        for value in values:
            if not value:
                continue
            # Keep the filter to the safe Azure resource type grammar. This is
            # interpolated into KQL only after validation to avoid query injection.
            if not re.fullmatch(r"[A-Za-z0-9._/\-]+", value):
                raise ValueError(f"Invalid Azure resource type filter: {value!r}")
            normalized.append(value)
        return sorted(set(normalized), key=str.casefold)

    @classmethod
    def build_resource_query(cls, resource_types: list[str] | None = None) -> str:
        query = cls.RESOURCE_QUERY
        if not resource_types:
            return query
        # RESOURCE_QUERY is a project/order pipeline; insert the type filter
        # before projection without changing the safe field subset.
        filters = " or ".join(f"type =~ '{item}'" for item in resource_types)
        return (
            "Resources\n"
            f"| where {filters}\n"
            "| project\n"
            "    id,\n"
            "    name,\n"
            "    type,\n"
            "    kind,\n"
            "    location,\n"
            "    resourceGroup,\n"
            "    subscriptionId,\n"
            "    tagsCount = array_length(bag_keys(tags)),\n"
            "    provisioningState = tostring(properties.provisioningState),\n"
            "    skuName = tostring(sku.name),\n"
            "    skuTier = tostring(sku.tier),\n"
            "    managedBy\n"
            "| order by type asc, id asc"
        ).strip()

    def inventory(
        self,
        *,
        profile_id: str = "all",
        subscription_ids: Iterable[str] | None = None,
        generate_excel: bool = True,
        resource_type: Any = None,
        resource_types: Any = None,
        resource_type_filter: Any = None,
    ) -> dict[str, Any]:
        """Discover non-secret resource metadata in enabled, accessible subscriptions.

        Optional resource type filters restrict the query to safe metadata for
        selected Azure resource types (for example VMs, storage accounts or SQL
        servers). Only the safe field subset is ever returned.
        """
        resource_type_filters = self._normalize_resource_types(
            resource_type=resource_type,
            resource_types=resource_types,
            resource_type_filter=resource_type_filter,
        )
        safe_result = {
            "cloud_resources_modified": False,
            "secrets_returned": False,
            "resource_type_filters": resource_type_filters,
        }
        if os.environ.get("SKYFALL_TEST_MODE") == "1":
            return {
                **safe_result,
                "success": False,
                "status": "blocked_test_mode",
                "error": "External Azure Resource Graph access is disabled in SKYFALL_TEST_MODE.",
            }

        requested_ids = [str(value).strip() for value in (subscription_ids or []) if str(value).strip()]
        normalized_requested = {value.casefold() for value in requested_ids}
        if len(normalized_requested) != len(requested_ids):
            raise ValueError("subscription_ids contains duplicate values.")

        profiles = self._profiles_to_process(profile_id)
        if not profiles:
            return {
                **safe_result,
                "success": False,
                "status": "failed",
                "error": "No Azure profiles are configured in SKYFALL.",
            }

        resources: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        subscriptions_seen: dict[str, dict[str, str]] = {}
        successful_profiles: list[str] = []
        requested_ids_found: set[str] = set()

        for profile in profiles:
            current_profile_id = str(profile["profile_id"])
            profile_name = str(profile["name"])
            auth = self.profile_manager.get_auth_status(current_profile_id)
            if not auth.get("authenticated"):
                errors.append({
                    "profile": profile_name,
                    "profile_id": current_profile_id,
                    "stage": "authentication",
                    "error": "Profile is not authenticated; sign in to this profile before inventory.",
                })
                continue

            subscription_result = self.profile_manager.list_subscriptions(current_profile_id, refresh=True)
            if not subscription_result.get("success"):
                errors.append({
                    "profile": profile_name,
                    "profile_id": current_profile_id,
                    "stage": "subscriptions",
                    "error": str(subscription_result.get("error") or "Subscription discovery failed."),
                })
                continue

            subscriptions = [
                item for item in subscription_result.get("subscriptions", [])
                if str(item.get("state", "")).casefold() == "enabled"
            ]
            if normalized_requested:
                subscriptions = [
                    item for item in subscriptions
                    if str(item.get("subscription_id", "")).casefold() in normalized_requested
                ]
                requested_ids_found.update(
                    str(item.get("subscription_id", "")).casefold() for item in subscriptions
                )
            if not subscriptions:
                # A target may be present in another configured profile.
                if normalized_requested:
                    continue
                errors.append({
                    "profile": profile_name,
                    "profile_id": current_profile_id,
                    "stage": "subscriptions",
                    "error": "No enabled accessible subscriptions were found for this profile.",
                })
                continue

            subscription_id_list = [str(item["subscription_id"]) for item in subscriptions]
            sub_by_id = {str(item.get("subscription_id", "")).casefold(): item for item in subscriptions}
            for item in subscriptions:
                sub_id = str(item.get("subscription_id", ""))
                subscriptions_seen[f"{current_profile_id}:{sub_id}".casefold()] = {
                    "profile_id": current_profile_id,
                    "profile": profile_name,
                    "subscription_id": sub_id,
                    "subscription_name": str(item.get("name", "")),
                    "tenant_id": str(item.get("tenant_id", "")),
                }

            try:
                arm_token = self.token_provider(current_profile_id)
                with self.http_client_factory() as client:
                    query = self.build_resource_query(resource_type_filters)
                    rows = self._query_resource_graph(
                        client, arm_token, subscription_id_list, query
                    )
                for row in rows:
                    resource_id = str(row.get("id") or "").strip()
                    name = str(row.get("name") or "").strip()
                    sub_id = str(row.get("subscriptionId") or "").strip()
                    if not resource_id or not name or sub_id.casefold() not in sub_by_id:
                        continue
                    sub = sub_by_id[sub_id.casefold()]
                    resources.append({
                        "profile_id": current_profile_id,
                        "profile": profile_name,
                        "subscription_id": sub_id,
                        "subscription_name": str(sub.get("name", "")),
                        "tenant_id": str(sub.get("tenant_id", "")),
                        "resource_group": str(row.get("resourceGroup") or ""),
                        "name": name,
                        "resource_type": str(row.get("type") or ""),
                        "kind": str(row.get("kind") or ""),
                        "region": str(row.get("location") or ""),
                        "tags_count": int(row.get("tagsCount") or 0) if str(row.get("tagsCount") or "").isdigit() else 0,
                        "provisioning_state": str(row.get("provisioningState") or ""),
                        "sku_name": str(row.get("skuName") or ""),
                        "sku_tier": str(row.get("skuTier") or ""),
                        "managed_by": str(row.get("managedBy") or ""),
                        "resource_id": resource_id,
                    })
                successful_profiles.append(profile_name)
            except Exception as exc:
                errors.append({
                    "profile": profile_name,
                    "profile_id": current_profile_id,
                    "stage": "resource_graph",
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                })

        if normalized_requested:
            missing = sorted(normalized_requested - requested_ids_found)
            if missing:
                errors.append({
                    "profile": "selected scope",
                    "profile_id": str(profile_id or "all"),
                    "stage": "subscription_filter",
                    "error": "Requested subscription IDs were not enabled or accessible to the selected profiles: "
                    + ", ".join(missing),
                })

        deduped: dict[str, dict[str, Any]] = {}
        for record in resources:
            key = f"{record['subscription_id']}:{record['resource_id']}".casefold()
            if key not in deduped:
                record["profiles"] = [record["profile"]]
                deduped[key] = record
            elif record["profile"] not in deduped[key]["profiles"]:
                deduped[key]["profiles"].append(record["profile"])
                deduped[key]["profile"] = "; ".join(sorted(deduped[key]["profiles"]))
        inventory = sorted(
            deduped.values(),
            key=lambda item: (
                item["subscription_name"].casefold(),
                item["resource_type"].casefold(),
                item["resource_group"].casefold(),
                item["name"].casefold(),
            ),
        )
        if not successful_profiles:
            return {
                **safe_result,
                "success": False,
                "status": "failed",
                "resource_count": 0,
                "errors": errors,
                "error": "No authenticated Azure profile completed resource discovery. Review the account and permission errors.",
            }

        type_counts = dict(sorted(Counter(row["resource_type"] for row in inventory).items()))
        report_path: str | None = None
        if generate_excel:
            scopes = {row["subscription_name"] for row in subscriptions_seen.values() if row["subscription_name"]}
            scope = next(iter(scopes)) if normalized_requested and len(scopes) == 1 else (
                "Selected-Subscriptions" if normalized_requested else "All-Subscriptions"
            )
            report_path = self._write_general_resource_report(inventory, errors, scope)

        return {
            **safe_result,
            "success": True,
            "status": "partial" if errors else "success",
            "operation": "azure_resource_inventory",
            "profile_count": len(successful_profiles),
            "subscription_count": len({row["subscription_id"] for row in subscriptions_seen.values()}),
            "resource_count": len(inventory),
            "resource_type_count": len(type_counts),
            "resource_type_counts": type_counts,
            "resource_type_filters": resource_type_filters,
            "errors": errors,
            "report": {"format": "xlsx", "path": report_path} if generate_excel else None,
            "preview": inventory[:20],
            "scope": "enabled_subscriptions_visible_to_selected_registered_azure_profile_or_profiles",
            "data_source": "Azure Resource Graph REST API",
            "cloud_resources_modified": False,
            "secrets_returned": False,
            "fields_returned": [
                "resource_id", "name", "resource_type", "kind", "region", "resource_group",
                "subscription_id", "subscription_name", "tenant_id", "tags_count",
                "provisioning_state", "sku_name", "sku_tier", "managed_by",
            ],
            "note": (
                "Only Resource Graph resource metadata fields are queried. Arbitrary resource properties, "
                "tags, app settings, connection strings, keys, and deployment or diagnostic data are excluded. "
                "Resource Graph indexing may lag recent changes."
            ),
        }

    def _write_general_resource_report(
        self, resources: list[dict[str, Any]], errors: list[dict[str, str]], scope: str
    ) -> str:
        report_dir = self.project_root / "reports" / "Azure"
        output_path = build_report_path(report_dir, ["Azure-Resource-Inventory", scope])
        temp_path = output_path.with_name(output_path.stem + ".tmp.xlsx")
        workbook = Workbook()
        summary = workbook.active
        summary.title = "Summary"
        summary.append(["SKYFALL Azure Resource Inventory", "Value"])
        summary.append(["Generated (UTC)", datetime.now(timezone.utc).isoformat()])
        summary.append(["Resources", len(resources)])
        summary.append(["Subscriptions", len({row["subscription_id"] for row in resources})])
        summary.append(["Resource types", len({row["resource_type"] for row in resources})])
        summary.append(["Discovery errors", len(errors)])
        self._append_table(
            workbook.create_sheet("Resources"),
            [
                ("Profile", "profile"), ("Profiles", "profiles"), ("Tenant ID", "tenant_id"),
                ("Subscription", "subscription_name"), ("Subscription ID", "subscription_id"),
                ("Resource Group", "resource_group"), ("Name", "name"), ("Type", "resource_type"),
                ("Kind", "kind"), ("Region", "region"), ("Tag Count", "tags_count"),
                ("Provisioning State", "provisioning_state"), ("SKU Name", "sku_name"),
                ("SKU Tier", "sku_tier"), ("Managed By", "managed_by"), ("Resource ID", "resource_id"),
            ],
            resources,
            "AzureResourcesTable",
        )
        self._append_table(
            workbook.create_sheet("Discovery Errors"),
            [("Profile", "profile"), ("Profile ID", "profile_id"), ("Stage", "stage"), ("Error", "error")],
            errors,
            "AzureResourceErrorsTable",
        )
        self._sanitize_workbook_text_cells(workbook)
        for sheet in workbook.worksheets:
            sheet.sheet_view.showGridLines = False
            sheet.freeze_panes = "A2"
            for cell in sheet[1]:
                cell.font = Font(name="Aptos Display", bold=True, color="FFFFFF", size=12)
                cell.fill = PatternFill("solid", fgColor="183A63")
                cell.alignment = Alignment(vertical="center", wrap_text=True)
            sheet.row_dimensions[1].height = 28
            for column_cells in sheet.columns:
                width = max(12, min(max((len(str(cell.value or "")) for cell in column_cells[:250]), default=10) + 2, 52))
                sheet.column_dimensions[column_cells[0].column_letter].width = width
        try:
            workbook.save(temp_path)
            os.replace(temp_path, output_path)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
        return str(output_path)
