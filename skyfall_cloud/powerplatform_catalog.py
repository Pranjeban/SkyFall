"""Power Platform flow, app, solution and connection inventory (v1.1 Modules 3.2-3.5).

Read-only metadata discovery through the official Power Platform REST APIs and
Dataverse Web API, authenticated by the unified MSAL identity authority.
Flow definitions, connection secrets and app packages are never retrieved.

HTTP is injected for contract testing. Environment URLs are host-allowlisted
to prevent server-side request forgery. Bearer tokens never enter results.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

from skyfall_cloud.msal_identity import POWER_PLATFORM_SCOPE, UnifiedIdentityAuthority
from skyfall_cloud.powerplatform_discovery import (
    PP_API_BASE,
    PowerPlatformDiscovery,
    PowerPlatformDiscoveryError,
)

_GUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_ALLOWED_DATAVERSE_HOSTS = (".crm.dynamics.com", ".dynamics.com")
_API_VERSION = "2024-10-01"
_DATAVERSE_VERSION = "v9.2"


class PowerPlatformCatalogError(RuntimeError):
    """User-facing catalog failure that never contains credential material."""


class PowerPlatformCatalog:
    """Read-only Power Platform application catalog."""

    def __init__(
        self,
        identity: UnifiedIdentityAuthority,
        *,
        http_client: Any = None,
    ) -> None:
        self.identity = identity
        self.http = http_client or httpx
        self.discovery = PowerPlatformDiscovery(identity, http_client=http_client)

    # -- internals ---------------------------------------------------------

    def _context(
        self, environment_id: str, profile_id: str | None
    ) -> tuple[Any, str]:
        try:
            profile = self.discovery._require_pp_profile(profile_id)
            clean_id = self.discovery._clean_environment_id(environment_id)
        except (PowerPlatformDiscoveryError, KeyError) as exc:
            raise PowerPlatformCatalogError(str(exc)) from exc
        return profile, clean_id

    @staticmethod
    def validate_environment_url(url: str) -> str:
        """Allow only HTTPS Dataverse hosts owned by Microsoft domains."""
        value = (url or "").strip().rstrip("/")
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or not any(host.endswith(suffix) and host != suffix.lstrip(".") for suffix in _ALLOWED_DATAVERSE_HOSTS)
        ):
            raise PowerPlatformCatalogError(
                "Environment URL must be an HTTPS Microsoft Dataverse URL selected from discovery."
            )
        return value

    def _fetch(
        self,
        url: str,
        profile: Any,
        *,
        version: str = _API_VERSION,
    ) -> list[dict[str, Any]]:
        token = self.identity.acquire_token(profile.profile_id, scopes=[POWER_PLATFORM_SCOPE])
        try:
            response = self.http.get(
                url,
                params={"api-version": version} if version == _API_VERSION else None,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=45,
            )
        except Exception as exc:
            raise PowerPlatformCatalogError("Power Platform catalog could not be reached.") from exc
        status = int(getattr(response, "status_code", 0) or 0)
        if status in (401, 403):
            raise PowerPlatformCatalogError(
                "Microsoft denied catalog access. Check this profile's permissions and consent."
            )
        if status >= 400:
            raise PowerPlatformCatalogError(f"Power Platform returned HTTP {status}.")
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise PowerPlatformCatalogError("Power Platform returned an unexpected response.") from exc
        rows = payload.get("value") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise PowerPlatformCatalogError("Power Platform returned an unexpected response.")
        return [row for row in rows if isinstance(row, dict)]

    @staticmethod
    def _first(row: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return str(value)[:500]
        return ""

    # -- catalog readers ---------------------------------------------------

    def list_flows(self, environment_id: str, profile_id: str | None = None) -> dict[str, Any]:
        profile, env_id = self._context(environment_id, profile_id)
        try:
            rows = self._fetch(
                f"{PP_API_BASE}/powerautomate/environments/{env_id}/flows", profile
            )
        except PowerPlatformCatalogError as exc:
            return {"success": False, "error": str(exc), "flows": [], "count": 0}
        flows = [{
            "flow_id": self._first(row, ("id", "flowId", "name")),
            "name": self._first(row, ("displayName", "name", "flowName")),
            "state": self._first(row, ("state", "status", "flowState")),
            "owner": self._first(row, ("createdBy", "owner", "creator")),
            "environment_id": env_id,
        } for row in rows]
        flows = [item for item in flows if item["flow_id"]]
        return {
            "success": True, "flows": flows, "count": len(flows),
            "profile_id": profile.profile_id, "environment_id": env_id,
        }

    def list_apps(self, environment_id: str, profile_id: str | None = None) -> dict[str, Any]:
        profile, env_id = self._context(environment_id, profile_id)
        try:
            rows = self._fetch(f"{PP_API_BASE}/powerapps/environments/{env_id}/apps", profile)
        except PowerPlatformCatalogError as exc:
            return {"success": False, "error": str(exc), "apps": [], "count": 0}
        apps = [{
            "app_id": self._first(row, ("id", "appId", "name")),
            "name": self._first(row, ("displayName", "name", "appName")),
            "app_type": self._first(row, ("appType", "type")),
            "state": self._first(row, ("state", "status")),
            "owner": self._first(row, ("createdBy", "owner")),
            "environment_id": env_id,
        } for row in rows]
        apps = [item for item in apps if item["app_id"]]
        return {
            "success": True, "apps": apps, "count": len(apps),
            "profile_id": profile.profile_id, "environment_id": env_id,
        }

    def list_solutions(
        self, environment_id: str, environment_url: str, profile_id: str | None = None
    ) -> dict[str, Any]:
        profile, env_id = self._context(environment_id, profile_id)
        base = self.validate_environment_url(environment_url)
        try:
            rows = self._fetch(
                f"{base}/api/data/{_DATAVERSE_VERSION}/solutions", profile,
                version=_DATAVERSE_VERSION,
            )
        except PowerPlatformCatalogError as exc:
            return {"success": False, "error": str(exc), "solutions": [], "count": 0}
        solutions = [{
            "solution_id": self._first(row, ("solutionid", "id")),
            "name": self._first(row, ("friendlyname", "displayName", "uniquename")),
            "unique_name": self._first(row, ("uniquename",)),
            "version": self._first(row, ("version",)),
            "managed": bool(row.get("ismanaged")),
            "publisher": self._first(row, ("publisherName", "publisher")),
            "environment_id": env_id,
        } for row in rows]
        solutions = [item for item in solutions if item["solution_id"]]
        return {
            "success": True, "solutions": solutions, "count": len(solutions),
            "profile_id": profile.profile_id, "environment_id": env_id,
        }

    def list_connections(
        self, environment_id: str, profile_id: str | None = None
    ) -> dict[str, Any]:
        profile, env_id = self._context(environment_id, profile_id)
        try:
            rows = self._fetch(
                f"{PP_API_BASE}/powerautomate/environments/{env_id}/connections", profile
            )
        except PowerPlatformCatalogError as exc:
            return {"success": False, "error": str(exc), "connections": [], "count": 0}
        connections = [{
            "connection_id": self._first(row, ("id", "connectionId", "name")),
            "name": self._first(row, ("displayName", "name", "connectionName")),
            "status": self._first(row, ("status", "connectionState", "state")),
            "owner": self._first(row, ("createdBy", "owner")),
            "environment_id": env_id,
        } for row in rows]
        connections = [item for item in connections if item["connection_id"]]
        return {
            "success": True, "connections": connections, "count": len(connections),
            "profile_id": profile.profile_id, "environment_id": env_id,
        }

    # -- intelligence ------------------------------------------------------

    @staticmethod
    def find_inactive_flows(flows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        active = {"started", "active", "enabled", "running"}
        return [flow for flow in flows if str(flow.get("state") or "").strip().lower() not in active]

    @staticmethod
    def find_broken_connections(connections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        broken = {"error", "failed", "disconnected", "broken", "invalid"}
        return [
            connection for connection in connections
            if str(connection.get("status") or "").strip().lower() in broken
        ]

    @staticmethod
    def compare_catalogs(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        keys = ("flows", "apps", "solutions", "connections")
        differences = [
            {"kind": key, "left": left.get(key, 0), "right": right.get(key, 0)}
            for key in keys
            if left.get(key, 0) != right.get(key, 0)
        ]
        return {
            "same": not differences,
            "differences": differences,
        }
