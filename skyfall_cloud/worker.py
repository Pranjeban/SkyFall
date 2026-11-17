"""Background workers for non-blocking Microsoft account discovery."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .azure_profiles import AzureProfileManager
from .powerplatform import PowerPlatformDiscovery
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
                    generate_excel=bool(self.params.get("generate_excel", True)),
                )
                if not payload.get("success"):
                    raise RuntimeError(payload.get("error") or "Power Automate flow inventory failed.")
            elif self.action == "powerplatform_profiles":
                discovery = PowerPlatformDiscovery()
                profiles = discovery.list_auth_profiles()
                auth = discovery.get_auth_status()
                payload = {
                    "profiles": profiles,
                    "auth": auth,
                    "environments": discovery.list_environments() if auth.get("authenticated") else {"success": False, "error": "No active PAC profile.", "environments": []},
                }
            elif self.action == "powerplatform_login":
                discovery = PowerPlatformDiscovery()
                payload = discovery.create_profile_and_login(
                    str(self.params.get("profile_name", "")),
                    str(self.params.get("environment", "")),
                )
                if not payload.get("success"):
                    raise RuntimeError(payload.get("error") or "Power Platform sign-in did not complete.")
            elif self.action == "powerplatform_select":
                discovery = PowerPlatformDiscovery()
                payload = discovery.select_profile(int(self.params.get("index", 0)))
                if not payload.get("success"):
                    raise RuntimeError(payload.get("error") or "Could not select PAC CLI profile.")
            elif self.action == "powerplatform_environments":
                discovery = PowerPlatformDiscovery()
                payload = {
                    "profiles": discovery.list_auth_profiles(),
                    "auth": discovery.get_auth_status(),
                    "environments": discovery.list_environments(),
                }
            else:
                raise ValueError(f"Unsupported Microsoft discovery action: {self.action}")
            self.completed.emit(self.action, payload)
        except Exception as exc:
            self.failed.emit(self.action, f"{type(exc).__name__}: {exc}")
