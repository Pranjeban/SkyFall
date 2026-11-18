"""Background workers for non-blocking Microsoft account discovery."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .azure_profiles import AzureProfileManager
from .powerplatform_accounts import PowerPlatformApi
from .azure_resources import AzureFunctionAppInventory
from .powerplatform_resources import PowerPlatformFlowInventory


class MicrosoftDiscoveryWorker(QThread):
    completed = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, action: str, profile_id: str = "azure-cli-default", params: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self.action = action
        self.profile_id = profile_id
        self.params = params or {}

    @staticmethod
    def _powerplatform_snapshot(discovery: PowerPlatformApi) -> dict:
        store = discovery.store
        rows = store.list_profiles()
        active_id = store.get_active_profile_id()
        active = store.get_profile(active_id)
        if active and active.get("azure_profile_id"):
            azure_status = AzureProfileManager().get_auth_status(str(active["azure_profile_id"]))
            authenticated = bool(azure_status.get("authenticated"))
            active = {
                **active,
                "username": active.get("username") or azure_status.get("user") or "",
                "tenant_id": active.get("tenant_id") or azure_status.get("tenant_id") or "",
            }
        else:
            authenticated = active is not None
        return {
            "profiles": {"success": True, "count": len(rows), "profiles": [{**item, "active": item.get("profile_id") == active_id} for item in rows]},
            "auth": {"authenticated": authenticated, "active_profile": active, "profile_count": len(rows)},
            "environments": discovery.list_environments() if active and authenticated else {"success": False, "error": "Add a profile and sign in to discover environments.", "environments": []},
        }

    def run(self) -> None:
        try:
            if self.action == "azure":
                manager = AzureProfileManager()
                status = manager.get_auth_status(self.profile_id)
                subscriptions = manager.list_subscriptions(self.profile_id, refresh=True)
                tenants = manager.list_tenants(self.profile_id, refresh=False)
                payload = {
                    "profile_id": self.profile_id,
                    "auth": status,
                    "subscriptions": subscriptions,
                    "tenants": tenants,
                    "profiles": manager.store.list_profiles(),
                }
            elif self.action == "azure_login":
                manager = AzureProfileManager()
                login = manager.login_profile(self.profile_id)
                if not login.get("success"):
                    raise RuntimeError(login.get("error") or "Azure sign-in did not complete.")
                payload = {
                    "profile_id": self.profile_id,
                    "login": login,
                    "auth": login.get("auth", manager.get_auth_status(self.profile_id)),
                    "subscriptions": login.get("subscriptions", manager.list_subscriptions(self.profile_id)),
                    "tenants": login.get("tenants", manager.list_tenants(self.profile_id)),
                    "profiles": manager.store.list_profiles(),
                }
            elif self.action == "azure_function_apps":
                profile_id = self.profile_id or "all"
                payload = AzureFunctionAppInventory().inventory(
                    profile_id=profile_id,
                    generate_excel=True,
                )
                if not payload.get("success"):
                    raise RuntimeError(payload.get("error") or "Azure Function App inventory failed.")
            elif self.action == "powerplatform_flow_inventory":
                inventory = PowerPlatformFlowInventory()
                payload = inventory.inventory(
                    environment_id=str(self.params.get("environment_id", "")),
                    environment_name=str(self.params.get("environment_name", "")),
                    environment_url=str(self.params.get("environment_url", "")),
                    profile_id=str(self.params.get("profile_id", "")) or None,
                    generate_excel=bool(self.params.get("generate_excel", True)),
                )
                if not payload.get("success"):
                    raise RuntimeError(payload.get("error") or "Power Automate flow inventory failed.")
            elif self.action == "powerplatform_profiles":
                discovery = PowerPlatformApi()
                payload = self._powerplatform_snapshot(discovery)
            elif self.action == "powerplatform_login":
                discovery = PowerPlatformApi()
                result = discovery.add_account(
                    str(self.params.get("profile_name", "")),
                    str(self.params.get("tenant", "organizations")),
                )
                if not result.get("success"):
                    raise RuntimeError(result.get("error") or "Power Platform sign-in did not complete.")
                payload = self._powerplatform_snapshot(discovery)
            elif self.action == "powerplatform_azure_login":
                manager = AzureProfileManager()
                profile = manager.store.create_profile(
                    str(self.params.get("profile_name", "")),
                    str(self.params.get("tenant", "")),
                    allow_tenant_discovery=True,
                )
                login = manager.login_profile(profile["profile_id"])
                if not login.get("success"):
                    manager.store.delete_profile(profile["profile_id"])
                    raise RuntimeError(login.get("error") or "Microsoft sign-in did not complete.")
                identity = login.get("auth") or {}
                discovery = PowerPlatformApi()
                discovery.attach_azure_profile(
                    profile["profile_id"],
                    name=profile["name"],
                    username=str(identity.get("user") or ""),
                    tenant_id=str(identity.get("tenant_id") or ""),
                )
                payload = self._powerplatform_snapshot(discovery)
            elif self.action == "powerplatform_select":
                discovery = PowerPlatformApi()
                discovery.select_profile(str(self.params.get("profile_id", "")))
                payload = self._powerplatform_snapshot(discovery)
            elif self.action == "powerplatform_environments":
                discovery = PowerPlatformApi()
                payload = self._powerplatform_snapshot(discovery)
            else:
                raise ValueError(f"Unsupported Microsoft discovery action: {self.action}")
            self.completed.emit(self.action, payload)
        except Exception as exc:
            self.failed.emit(self.action, f"{type(exc).__name__}: {exc}")
