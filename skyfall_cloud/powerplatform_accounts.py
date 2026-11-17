"""Per-user Power Platform OAuth profiles and read-only REST discovery.

Tokens are cached per SKYFALL profile using MSAL Extensions' platform
protection (Windows DPAPI). Profile metadata contains no credentials.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx


API_SCOPE = "https://api.powerplatform.com/.default"
API_BASE = "https://api.powerplatform.com"
API_VERSION = "2024-10-01"
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _safe_next_link(current_url: str, candidate: Any, allowed_host: str) -> str:
    value = str(candidate or "").strip()
    if not value:
        return ""
    resolved = urljoin(current_url, value)
    parsed = urlparse(resolved)
    if parsed.scheme != "https" or parsed.hostname != allowed_host or parsed.username or parsed.password:
        raise RuntimeError("Microsoft returned an invalid pagination link; the request was stopped before sending credentials.")
    return resolved


def _local_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SKYFALL" / "powerplatform"


class PowerPlatformAccountStore:
    """Persistent profile registry with per-profile OS-protected MSAL caches."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else _local_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "profiles.json"

    def _read(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"schema_version": 1, "client_id": "", "active_profile_id": None, "profiles": []}
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Power Platform profile registry could not be read: {exc}") from exc
        if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("profiles"), list):
            raise ValueError("Power Platform profile registry has an unsupported format.")
        data.setdefault("client_id", "")
        data.setdefault("active_profile_id", None)
        return data

    def _write(self, data: dict[str, Any]) -> None:
        temporary = self.registry_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, self.registry_path)

    def get_client_id(self) -> str:
        return str(os.environ.get("SKYFALL_POWERPLATFORM_CLIENT_ID") or self._read().get("client_id") or "").strip()

    def set_client_id(self, client_id: str) -> None:
        value = (client_id or "").strip()
        if not _GUID.fullmatch(value):
            raise ValueError("Enter the Application (client) ID GUID from your Microsoft Entra app registration.")
        data = self._read()
        data["client_id"] = value
        self._write(data)

    def list_profiles(self) -> list[dict[str, Any]]:
        data = self._read()
        return [
            {key: item.get(key) for key in (
                "profile_id", "name", "username", "tenant_id", "created_at", "selected_environment_id"
            )}
            for item in data["profiles"]
        ]

    def get_active_profile_id(self) -> str | None:
        return self._read().get("active_profile_id")

    def get_profile(self, profile_id: str | None = None) -> dict[str, Any] | None:
        data = self._read()
        target = profile_id or data.get("active_profile_id")
        return next((dict(item) for item in data["profiles"] if item.get("profile_id") == target), None)

    def upsert_profile(self, profile: dict[str, Any], *, activate: bool = True) -> None:
        data = self._read()
        profiles = data["profiles"]
        existing_index = next((i for i, item in enumerate(profiles) if item.get("profile_id") == profile["profile_id"]), None)
        if existing_index is None:
            profiles.append(profile)
        else:
            profiles[existing_index] = {**profiles[existing_index], **profile}
        if activate:
            data["active_profile_id"] = profile["profile_id"]
        self._write(data)

    def select_profile(self, profile_id: str) -> dict[str, Any]:
        data = self._read()
        profile = next((item for item in data["profiles"] if item.get("profile_id") == profile_id), None)
        if profile is None:
            raise KeyError("The selected Power Platform account profile no longer exists.")
        data["active_profile_id"] = profile_id
        self._write(data)
        return dict(profile)

    def set_selected_environment(self, profile_id: str, environment_id: str) -> None:
        data = self._read()
        profile = next((item for item in data["profiles"] if item.get("profile_id") == profile_id), None)
        if profile is None:
            raise KeyError("The selected Power Platform account profile no longer exists.")
        profile["selected_environment_id"] = environment_id
        self._write(data)

    def remove_profile(self, profile_id: str) -> None:
        data = self._read()
        data["profiles"] = [item for item in data["profiles"] if item.get("profile_id") != profile_id]
        if data.get("active_profile_id") == profile_id:
            data["active_profile_id"] = data["profiles"][0]["profile_id"] if data["profiles"] else None
        self._write(data)
        cache_file = self.root / "token_cache" / f"{profile_id}.bin"
        if cache_file.exists():
            cache_file.unlink()

    def token_cache_path(self, profile_id: str) -> Path:
        folder = self.root / "token_cache"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{profile_id}.bin"


class PowerPlatformApi:
    """Delegated OAuth access to Power Platform and Dataverse read APIs."""

    def __init__(self, store: PowerPlatformAccountStore | None = None, *, http_client=httpx) -> None:
        self.store = store or PowerPlatformAccountStore()
        self.http = http_client

    def _client(self, profile_id: str, *, authority_tenant: str | None = None):
        try:
            import msal
            from msal_extensions import PersistedTokenCache
            from msal_extensions.persistence import build_encrypted_persistence
        except ImportError as exc:
            raise RuntimeError("Install the SKYFALL requirements to enable direct Microsoft sign-in (MSAL).") from exc
        client_id = self.store.get_client_id()
        if not client_id:
            raise RuntimeError("Configure a Microsoft Entra application client ID in Power Platform settings first.")
        profile = self.store.get_profile(profile_id)
        tenant = authority_tenant or (profile or {}).get("tenant_id") or "organizations"
        cache = PersistedTokenCache(build_encrypted_persistence(str(self.store.token_cache_path(profile_id))))
        app = msal.PublicClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant}",
            token_cache=cache,
        )
        return app, cache

    @staticmethod
    def _token_error(result: dict[str, Any]) -> str:
        # Return safe user-facing identity errors, never raw token responses.
        code = str(result.get("error") or "authentication_failed")
        if code in {"invalid_client", "unauthorized_client"}:
            return "Microsoft rejected the app registration. Check the client ID and enable public client flows for desktop sign-in."
        if code in {"interaction_required", "login_required", "consent_required"}:
            return "This profile needs Microsoft sign-in again. Select Add Microsoft account to reconnect it."
        return f"Microsoft sign-in failed ({code}). Check app registration permissions and tenant consent."

    def add_account(self, profile_name: str, tenant: str = "organizations") -> dict[str, Any]:
        name = (profile_name or "").strip()
        if not name or len(name) > 80:
            raise ValueError("Enter an account profile name between 1 and 80 characters.")
        clean_tenant = (tenant or "organizations").strip()
        if len(clean_tenant) > 200 or any(c in clean_tenant for c in "\r\n/\\"):
            raise ValueError("Enter a tenant ID, tenant domain, or leave it blank for work and school accounts.")
        profile_id = str(uuid.uuid4())
        app, _cache = self._client(profile_id, authority_tenant=clean_tenant or "organizations")
        try:
            result = app.acquire_token_interactive(
                scopes=[API_SCOPE],
                prompt="select_account",
                timeout=300,
            )
        except Exception as exc:
            raise RuntimeError(f"Microsoft browser sign-in could not complete: {type(exc).__name__}.") from exc
        if not result or not result.get("access_token"):
            raise RuntimeError(self._token_error(result or {}))
        account = result.get("id_token_claims") or {}
        profile = {
            "profile_id": profile_id,
            "name": name,
            "username": str(account.get("preferred_username") or "Signed-in Microsoft account")[:200],
            "tenant_id": str(account.get("tid") or clean_tenant)[:200],
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "selected_environment_id": "",
        }
        self.store.upsert_profile(profile)
        return {"success": True, "profile": profile}

    def select_profile(self, profile_id: str) -> dict[str, Any]:
        profile = self.store.select_profile(profile_id)
        return {"success": True, "profile": profile}

    def remove_profile(self, profile_id: str) -> None:
        self.store.remove_profile(profile_id)

    def _access_token(self, profile_id: str, scopes: list[str], *, interactive: bool = False) -> str:
        profile = self.store.get_profile(profile_id)
        if profile is None:
            raise RuntimeError("Select a saved Power Platform account before continuing.")
        app, _cache = self._client(profile_id)
        accounts = app.get_accounts(username=profile.get("username"))
        result = app.acquire_token_silent(scopes, account=accounts[0]) if accounts else None
        if not result and interactive:
            try:
                result = app.acquire_token_interactive(scopes=scopes, prompt="select_account", timeout=300)
            except Exception as exc:
                raise RuntimeError(f"Microsoft sign-in could not complete: {type(exc).__name__}.") from exc
        if not result or not result.get("access_token"):
            raise RuntimeError(self._token_error(result or {"error": "interaction_required"}))
        return str(result["access_token"])

    def list_environments(self, profile_id: str | None = None) -> dict[str, Any]:
        target = profile_id or self.store.get_active_profile_id()
        if not target:
            return {"success": False, "error": "Add or select a Microsoft account profile first.", "environments": []}
        try:
            token = self._access_token(target, [API_SCOPE])
            url = f"{API_BASE}/environmentmanagement/environments"
            params: dict[str, Any] | None = {"api-version": API_VERSION, "$top": 100}
            rows: list[dict[str, Any]] = []
            page_count = 0
            while url:
                page_count += 1
                if page_count > 100:
                    raise RuntimeError("Environment discovery exceeded the 100-page safety limit.")
                response = self.http.get(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    timeout=45,
                )
                params = None
                if response.status_code >= 400:
                    return {
                        "success": False,
                        "error": self._http_error(response.status_code),
                        "diagnostic_code": self._diagnostic_code(response.status_code),
                        "http_status": response.status_code,
                        "environments": [],
                    }
                data = response.json()
                for item in data.get("value", []) if isinstance(data, dict) else []:
                    if not isinstance(item, dict):
                        continue
                    rows.append({
                        "name": str(item.get("displayName") or item.get("name") or "Unnamed environment"),
                        "type": str(item.get("type") or "Environment"),
                        "environment_id": str(item.get("id") or "").strip("{}"),
                        "environment_url": str(item.get("url") or ""),
                        "organization_id": str(item.get("dataverseId") or ""),
                        "region": str(item.get("geo") or item.get("azureRegion") or ""),
                        "tenant_id": str(item.get("tenantId") or ""),
                        "state": str(item.get("state") or ""),
                    })
                next_link = (data.get("@odata.nextLink") or data.get("@odata.nextlink")) if isinstance(data, dict) else ""
                url = _safe_next_link(url, next_link, "api.powerplatform.com")
            return {"success": True, "count": len(rows), "environments": rows, "discovery_format": "power_platform_rest_api", "profile_id": target}
        except Exception as exc:
            return {"success": False, "error": str(exc)[:700], "environments": [], "profile_id": target}

    def list_flows(self, profile_id: str, environment_url: str) -> list[dict[str, Any]]:
        base = (environment_url or "").strip().rstrip("/")
        parsed = urlparse(base)
        if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith((".dynamics.com", ".crm.dynamics.com")):
            raise ValueError("Selected environment does not have a valid HTTPS Dataverse URL.")
        scope = f"{base}/.default"
        token = self._access_token(profile_id, [scope], interactive=True)
        url = f"{base}/api/data/v9.2/workflows"
        params = {
            "$select": "workflowid,name,category,statecode,statuscode,createdon,modifiedon,_ownerid_value",
            "$filter": "category eq 5",
            "$orderby": "name asc",
            "$top": "5000",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Prefer": 'odata.include-annotations="*"',
        }
        rows: list[dict[str, Any]] = []
        page_count = 0
        while url:
            page_count += 1
            if page_count > 100:
                raise RuntimeError("Flow inventory exceeded the 100-page safety limit.")
            response = self.http.get(url, params=params, headers=headers, timeout=90)
            params = None
            if response.status_code >= 400:
                raise RuntimeError(self._http_error(response.status_code, dataverse=True))
            data = response.json()
            for row in data.get("value", []) if isinstance(data, dict) else []:
                if not isinstance(row, dict):
                    continue
                state = row.get("statecode@OData.Community.Display.V1.FormattedValue")
                if state is None:
                    state = "Enabled" if row.get("statecode") == 1 else "Disabled" if row.get("statecode") == 0 else "Unknown"
                rows.append({
                    "workflowId": row.get("workflowid"),
                    "displayName": row.get("name"),
                    "state": state,
                    "flowType": row.get("category@OData.Community.Display.V1.FormattedValue") or "Cloud flow",
                    "owner": {"displayName": row.get("_ownerid_value@OData.Community.Display.V1.FormattedValue")},
                    "createdOn": row.get("createdon"),
                    "modifiedOn": row.get("modifiedon"),
                })
            next_link = data.get("@odata.nextLink") if isinstance(data, dict) else ""
            url = _safe_next_link(url, next_link, parsed.hostname)
        return rows

    @staticmethod
    def _diagnostic_code(status: int) -> str:
        if status in (401, 403):
            return "powerplatform_permission_denied"
        if status == 404:
            return "powerplatform_endpoint_not_found"
        if status == 429:
            return "powerplatform_throttled"
        return "powerplatform_api_error"

    @staticmethod
    def _http_error(status: int, *, dataverse: bool = False) -> str:
        if status in (401, 403):
            if dataverse:
                return "Microsoft denied Dataverse flow metadata access. Confirm the app has delegated Dynamics CRM user_impersonation consent and that your account can read cloud flows in this environment."
            return "Microsoft denied environment discovery. Confirm Power Platform API delegated environment read permission and tenant consent for this app."
        if status == 404:
            return "The selected environment or Power Platform API endpoint was not found. Refresh environment discovery and try again."
        if status == 429:
            return "Microsoft throttled this request. Wait briefly, then retry."
        return f"Microsoft Power Platform API request failed (HTTP {status}). Check network access and app permissions."
