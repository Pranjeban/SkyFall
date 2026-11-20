"""Power Platform environment intelligence (v1.1 Module 3.1).

Read-only discovery through the official Power Platform environment management
API, authenticated by the unified MSAL identity authority. Power Platform
sessions are independent from Azure sessions: an Azure profile is rejected.

No live tenant is needed -- the HTTP client is injected for contract tests.
Bearer tokens never appear in returned data, errors or diagnostics.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from skyfall_cloud.msal_identity import POWER_PLATFORM_SCOPE, UnifiedIdentityAuthority

PP_API_BASE = "https://api.powerplatform.com"
ENVIRONMENTS_PATH = "/environmentmanagement/environments"
API_VERSION = "2024-10-01"
_GUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class PowerPlatformDiscoveryError(RuntimeError):
    """User-facing discovery failure that never contains credential material."""


class PowerPlatformDiscovery:
    """Environment inventory, detail, comparison and session switching."""

    def __init__(
        self,
        identity: UnifiedIdentityAuthority,
        *,
        http_client: Any = None,
    ) -> None:
        self.identity = identity
        self.http = http_client or httpx
        self._active_environment: dict[str, str] = {}

    # -- internals ---------------------------------------------------------

    def _require_pp_profile(self, profile_id: str | None) -> Any:
        if profile_id is None:
            profile_id = self.identity.registry.get_active_profile_id("powerplatform")
        profile = self.identity.registry.get_profile(profile_id)
        if profile is None:
            raise KeyError("Select a Power Platform identity profile before discovery.")
        if profile.provider != "powerplatform":
            raise ValueError(
                "This identity profile is for Azure. Power Platform discovery requires a separate sign-in."
            )
        return profile

    @staticmethod
    def _clean_environment_id(value: str) -> str:
        cleaned = str(value or "").strip().strip("{}")
        if not _GUID.fullmatch(cleaned):
            raise PowerPlatformDiscoveryError(
                "Environment ID must be a valid GUID selected from discovered environments."
            )
        return cleaned

    def _get(self, url: str, profile_id: str | None) -> Any:
        profile = self._require_pp_profile(profile_id)
        token = self.identity.acquire_token(profile.profile_id, scopes=[POWER_PLATFORM_SCOPE])
        try:
            response = self.http.get(
                url,
                params={"api-version": API_VERSION},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=45,
            )
        except Exception as exc:
            raise PowerPlatformDiscoveryError("Power Platform could not be reached.") from exc
        status = int(getattr(response, "status_code", 0) or 0)
        if status in (401, 403):
            raise PowerPlatformDiscoveryError(
                "Microsoft denied Power Platform access. Check this profile's permissions and consent."
            )
        if status >= 400:
            raise PowerPlatformDiscoveryError(f"Power Platform returned HTTP {status}.")
        try:
            return response.json()
        except (ValueError, TypeError) as exc:
            raise PowerPlatformDiscoveryError("Power Platform returned an unexpected response.") from exc

    @staticmethod
    def _record(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "environment_id": str(item.get("id") or "").strip("{}"),
            "name": str(item.get("displayName") or item.get("name") or "Unnamed environment"),
            "type": str(item.get("type") or item.get("environmentSku") or ""),
            "environment_url": str(item.get("url") or ""),
            "region": str(item.get("azureRegion") or item.get("geo") or ""),
            "state": str(item.get("state") or ""),
            "tenant_id": str(item.get("tenantId") or ""),
            "organization_id": str(item.get("dataverseId") or item.get("organizationId") or ""),
            "is_default": bool(item.get("isDefault")),
            "created_at": str(item.get("createdTime") or ""),
        }

    # -- public discovery --------------------------------------------------

    def list_environments(self, profile_id: str | None = None) -> dict[str, Any]:
        profile = self._require_pp_profile(profile_id)
        try:
            payload = self._get(f"{PP_API_BASE}{ENVIRONMENTS_PATH}", profile.profile_id)
            rows = payload.get("value") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                raise PowerPlatformDiscoveryError("Power Platform returned an unexpected response.")
        except (PowerPlatformDiscoveryError, RuntimeError, KeyError) as exc:
            return {
                "success": False,
                "error": str(exc),
                "environments": [],
                "count": 0,
            }
        environments = [self._record(item) for item in rows if isinstance(item, dict)]
        environments = [item for item in environments if item["environment_id"]]
        return {
            "success": True,
            "environments": environments,
            "count": len(environments),
            "discovery_method": "power_platform_rest_api",
            "profile_id": profile.profile_id,
        }

    def get_environment(
        self, environment_id: str, profile_id: str | None = None
    ) -> dict[str, Any]:
        """Inspect one environment's details, security flags and capacity hints."""
        profile = self._require_pp_profile(profile_id)
        clean_id = self._clean_environment_id(environment_id)
        payload = self._get(
            f"{PP_API_BASE}{ENVIRONMENTS_PATH}/{clean_id}", profile.profile_id
        )
        if not isinstance(payload, dict):
            raise PowerPlatformDiscoveryError("Power Platform returned an unexpected response.")
        record = self._record(payload)
        flags = {
            key: bool(payload[key])
            for key in (
                "isDefault", "supportsImageEditing", "supportsPdfEditing",
                "isDisabled", "vetoProtectionEnabled",
            )
            if key in payload
        }
        capacity = payload.get("capacity") if isinstance(payload.get("capacity"), dict) else {}
        record["security_flags"] = flags
        record["capacity"] = capacity
        record["owners"] = [
            str(owner.get("displayName") or owner.get("id") or "")
            for owner in (payload.get("owners") or [])
            if isinstance(owner, dict)
        ]
        return record

    def select_environment(self, environment_id: str, profile_id: str | None = None) -> dict[str, Any]:
        """Switch the active environment for this Power Platform profile."""
        profile = self._require_pp_profile(profile_id)
        clean_id = self._clean_environment_id(environment_id)
        self._active_environment[profile.profile_id] = clean_id
        return {"profile_id": profile.profile_id, "active_environment_id": clean_id}

    def active_environment(self, profile_id: str | None = None) -> str | None:
        profile = self._require_pp_profile(profile_id)
        return self._active_environment.get(profile.profile_id)

    @staticmethod
    def compare_environments(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        """Compare two environment records (spec §3.1 environment comparison)."""
        fields = ("name", "type", "region", "state", "tenant_id", "organization_id")
        differences = [
            {"field": field, "left": left.get(field), "right": right.get(field)}
            for field in fields
            if left.get(field) != right.get(field)
        ]
        return {
            "left": left.get("environment_id"),
            "right": right.get("environment_id"),
            "same": not differences,
            "differences": differences,
        }
