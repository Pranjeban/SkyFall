"""Background workers for non-blocking Microsoft account discovery."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .azure_profiles import AzureProfileManager
from .powerplatform import PowerPlatformDiscovery


class MicrosoftDiscoveryWorker(QThread):
    completed = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, action: str, profile_id: str = "azure-cli-default", parent=None) -> None:
        super().__init__(parent)
        self.action = action
        self.profile_id = profile_id

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
            elif self.action == "powerplatform_profiles":
                discovery = PowerPlatformDiscovery()
                payload = {
                    "profiles": discovery.list_auth_profiles(),
                    "auth": discovery.get_auth_status(),
                }
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
