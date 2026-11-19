"""Unified identity and authentication health service (Phase 1).

Aggregates Azure CLI profile auth state and Power Platform account state into a
single, secret-free view. No tokens or credential material are ever returned.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable


@dataclass
class IdentityHealth:
    provider: str  # "azure" or "powerplatform"
    profile_id: str
    profile_name: str
    authenticated: bool
    detail: str
    tenant_id: str = ""
    user: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IdentityService:
    """Aggregates auth health across Azure and Power Platform providers."""

    def __init__(
        self,
        azure_manager: Any = None,
        powerplatform_store: Any = None,
    ) -> None:
        self.azure_manager = azure_manager
        self.powerplatform_store = powerplatform_store

    def azure_health(self) -> list[IdentityHealth]:
        if self.azure_manager is None:
            return []
        try:
            status = self.azure_manager.get_auth_status("all")
        except Exception as exc:  # pragma: no cover - defensive
            return [IdentityHealth(provider="azure", profile_id="all", profile_name="all", authenticated=False, detail=str(exc))]
        results: list[IdentityHealth] = []
        profiles = status.get("profiles") if isinstance(status, dict) else None
        if isinstance(profiles, list):
            for p in profiles:
                results.append(IdentityHealth(
                    provider="azure",
                    profile_id=str(p.get("profile_id", "")),
                    profile_name=str(p.get("profile", "")),
                    authenticated=bool(p.get("authenticated", False)),
                    detail="" if p.get("authenticated") else str(p.get("error", "not authenticated")),
                    tenant_id=str(p.get("tenant_id", "") or ""),
                    user=str(p.get("user", "") or ""),
                ))
        else:
            results.append(IdentityHealth(
                provider="azure",
                profile_id=str(status.get("profile_id", "all")),
                profile_name="all",
                authenticated=bool(status.get("authenticated", False)),
                detail="" if status.get("authenticated") else str(status.get("error", "not authenticated")),
                tenant_id=str(status.get("tenant_id", "") or ""),
                user=str(status.get("user", "") or ""),
            ))
        return results

    def powerplatform_health(self) -> list[IdentityHealth]:
        if self.powerplatform_store is None:
            return []
        try:
            accounts = self.powerplatform_store.list_accounts() if hasattr(self.powerplatform_store, "list_accounts") else []
        except Exception as exc:  # pragma: no cover - defensive
            return [IdentityHealth(provider="powerplatform", profile_id="all", profile_name="all", authenticated=False, detail=str(exc))]
        results: list[IdentityHealth] = []
        for acc in accounts or []:
            results.append(IdentityHealth(
                provider="powerplatform",
                profile_id=str(acc.get("profile_id", acc.get("id", ""))),
                profile_name=str(acc.get("name", acc.get("profile_name", ""))),
                authenticated=True,
                detail="registered",
                tenant_id=str(acc.get("tenant_id", "") or ""),
                user=str(acc.get("username", "") or ""),
            ))
        if not results:
            results.append(IdentityHealth(provider="powerplatform", profile_id="none", profile_name="none", authenticated=False, detail="no accounts registered"))
        return results

    def overall_health(self) -> dict[str, Any]:
        az = self.azure_health()
        pp = self.powerplatform_health()
        return {
            "azure": [h.to_dict() for h in az],
            "powerplatform": [h.to_dict() for h in pp],
            "azure_authenticated_count": sum(1 for h in az if h.authenticated),
            "powerplatform_authenticated_count": sum(1 for h in pp if h.authenticated),
            "credential_material_returned": False,
        }
