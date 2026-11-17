"""Azure CLI profile discovery using isolated AZURE_CONFIG_DIR profiles.

The default profile reads the user's existing Azure CLI configuration without
changing it. Additional SKYFALL profiles receive their own AZURE_CONFIG_DIR,
so signing into another account does not overwrite or switch the user's normal
Azure CLI profile.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .command_runner import CommandResult, run_cli


Runner = Callable[..., CommandResult]


def _local_app_data() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root)
    return Path.home() / "AppData" / "Local"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_profile_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")[:32]
    return f"{slug or 'azure-account'}-{uuid.uuid4().hex[:8]}"


def _parse_json(text: str, label: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Azure CLI returned invalid JSON for {label}: {exc.msg}") from exc


class AzureProfileStore:
    """Stores profile metadata only. Azure CLI owns and protects token caches."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else _local_app_data() / "SKYFALL" / "azure_profiles"
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "profiles.json"

    def _read(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"schema_version": 1, "profiles": []}
        try:
            raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Azure profile registry cannot be read: {exc}") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != 1 or not isinstance(raw.get("profiles"), list):
            raise ValueError("Azure profile registry has an unsupported schema.")
        return raw

    def _write(self, data: dict[str, Any]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.registry_path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, self.registry_path)

    def list_profiles(self) -> list[dict[str, Any]]:
        profiles = [{
            "profile_id": "azure-cli-default",
            "name": "Default Azure CLI",
            "kind": "existing_cli_profile",
            "config_dir": None,
            "created_at": None,
            "tenant_hint": None,
        }]
        resolved_root = self.root.resolve()
        for item in self._read()["profiles"]:
            # Only accept isolated config directories contained under SKYFALL's
            # dedicated profile root; a modified registry cannot redirect the
            # Azure CLI at an arbitrary credential directory.
            profile_id = str(item.get("profile_id", ""))
            if not re.fullmatch(r"[a-z0-9-]{1,80}", profile_id):
                raise ValueError("Azure profile registry contains an invalid profile ID.")
            config_dir = Path(str(item.get("config_dir", ""))).resolve()
            if not config_dir.is_relative_to(resolved_root):
                raise ValueError("Azure profile config directory is outside SKYFALL's managed profile root.")
            # Only known, non-secret metadata fields are returned.
            profiles.append({
                "profile_id": profile_id,
                "name": str(item.get("name", "Azure account")),
                "kind": "skyfall_isolated_profile",
                "config_dir": str(config_dir),
                "created_at": item.get("created_at"),
                "tenant_hint": item.get("tenant_hint"),
            })
        return profiles

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        clean = (profile_id or "azure-cli-default").strip()
        for profile in self.list_profiles():
            if profile["profile_id"] == clean:
                return profile
        raise KeyError(f"Unknown Azure profile: {clean}")

    def create_profile(self, name: str, tenant_hint: str | None = None) -> dict[str, Any]:
        clean_name = (name or "").strip()
        if not clean_name or len(clean_name) > 80:
            raise ValueError("Profile name must contain 1 to 80 characters.")
        tenant = (tenant_hint or "").strip() or None
        if tenant and (len(tenant) > 200 or any(ch in tenant for ch in "\r\n\x00")):
            raise ValueError("Tenant identifier is invalid.")

        data = self._read()
        if any(str(p.get("name", "")).casefold() == clean_name.casefold() for p in data["profiles"]):
            raise ValueError(f"An Azure profile named '{clean_name}' already exists.")

        profile_id = _safe_profile_id(clean_name)
        config_dir = self.root / profile_id / "azure-cli"
        config_dir.mkdir(parents=True, exist_ok=True)
        item = {
            "profile_id": profile_id,
            "name": clean_name,
            "config_dir": str(config_dir.resolve()),
            "tenant_hint": tenant,
            "created_at": _utc_now(),
        }
        data["profiles"].append(item)
        self._write(data)
        profile = self.get_profile(profile_id)
        profile["login_command"] = self.login_command(profile)
        return profile

    @staticmethod
    def login_command(profile: dict[str, Any]) -> str:
        config_dir = str(profile.get("config_dir", ""))
        # PowerShell single-quoted string escaping.
        escaped_path = config_dir.replace("'", "''")
        command = f"$env:AZURE_CONFIG_DIR = '{escaped_path}'`naz login --use-device-code"
        tenant = str(profile.get("tenant_hint") or "").strip()
        if tenant:
            escaped_tenant = tenant.replace("'", "''")
            command += f" --tenant '{escaped_tenant}'"
        return command


class AzureProfileManager:
    def __init__(
        self,
        store: AzureProfileStore | None = None,
        runner: Runner = run_cli,
    ) -> None:
        self.store = store or AzureProfileStore()
        self.runner = runner

    def _env_for(self, profile_id: str) -> dict[str, str | None]:
        profile = self.store.get_profile(profile_id)
        if profile["profile_id"] == "azure-cli-default":
            # Respect an explicitly configured Azure CLI profile in the parent
            # process; otherwise inherit the standard ~/.azure profile.
            return {}
        return {"AZURE_CONFIG_DIR": str(profile["config_dir"])}

    def get_auth_status(self, profile_id: str = "all") -> dict[str, Any]:
        """Inspect one Azure profile or all profiles without changing any context."""
        clean = (profile_id or "all").strip()
        if clean.lower() not in {"all", "*"}:
            return self._get_auth_status_single(clean)
        results = [self._get_auth_status_single(p["profile_id"]) for p in self.store.list_profiles()]
        authenticated = [item for item in results if item.get("authenticated")]
        return {
            "authenticated": bool(authenticated),
            "profile_id": "all",
            "profile_count": len(results),
            "authenticated_profile_count": len(authenticated),
            "profiles": results,
            "scope": "all_registered_skyfall_azure_cli_profiles",
            "credential_material_returned": False,
        }

    def list_subscriptions(self, profile_id: str = "all", refresh: bool = False) -> dict[str, Any]:
        """List cached/accessible subscriptions for one profile or all registered profiles."""
        clean = (profile_id or "all").strip()
        if clean.lower() not in {"all", "*"}:
            return self._list_subscriptions_single(clean, refresh=refresh)
        results = [
            self._list_subscriptions_single(p["profile_id"], refresh=refresh)
            for p in self.store.list_profiles()
        ]
        merged: list[dict[str, Any]] = []
        for result in results:
            if result.get("success"):
                for item in result.get("subscriptions", []):
                    merged.append({**item, "profile_id": result.get("profile_id"), "profile": result.get("profile")})
        errors = [
            {"profile_id": item.get("profile_id"), "profile": item.get("profile"), "error": item.get("error")}
            for item in results if not item.get("success")
        ]
        successful_count = sum(1 for item in results if item.get("success"))
        return {
            "success": successful_count > 0,
            "profile_id": "all",
            "profile_count": len(results),
            "successful_profile_count": successful_count,
            "failed_profiles": errors,
            "partial_success": successful_count > 0 and bool(errors),
            "refresh_requested": refresh,
            "count": len(merged),
            "subscriptions": merged,
            "scope": "all_registered_skyfall_azure_cli_profiles",
        }

    def list_tenants(self, profile_id: str = "all", refresh: bool = False) -> dict[str, Any]:
        """List deduplicated tenant IDs for one or all registered Azure profiles."""
        clean = (profile_id or "all").strip()
        if clean.lower() not in {"all", "*"}:
            return self._list_tenants_single(clean, refresh=refresh)
        results = [
            self._list_tenants_single(p["profile_id"], refresh=refresh)
            for p in self.store.list_profiles()
        ]
        tenant_map: dict[str, set[str]] = {}
        errors: list[dict[str, str]] = []
        for result in results:
            if not result.get("success"):
                errors.append({"profile_id": str(result.get("profile_id", "")), "error": str(result.get("error", "Tenant discovery failed."))})
                continue
            for item in result.get("tenants", []):
                tenant_id = str(item.get("tenant_id", ""))
                if tenant_id:
                    tenant_map.setdefault(tenant_id, set()).add(str(result.get("profile_id", "")))
        tenants = [
            {"tenant_id": tenant_id, "profile_ids": sorted(profile_ids)}
            for tenant_id, profile_ids in sorted(tenant_map.items())
        ]
        successful_count = sum(1 for item in results if item.get("success"))
        return {
            "success": successful_count > 0,
            "profile_id": "all",
            "profile_count": len(results),
            "successful_profile_count": successful_count,
            "count": len(tenants),
            "tenants": tenants,
            "failed_profiles": errors,
            "partial_success": successful_count > 0 and bool(errors),
            "discovery_method": "deduplicated_tenant_ids_across_registered_azure_cli_profiles",
        }

    def _get_auth_status_single(self, profile_id: str) -> dict[str, Any]:
        profile = self.store.get_profile(profile_id)
        try:
            result = self.runner("az", ["account", "show", "--output", "json"], timeout_seconds=30, env_overrides=self._env_for(profile_id))
        except FileNotFoundError as exc:
            return {"authenticated": False, "profile": profile["name"], "error": str(exc)}
        if not result.succeeded:
            message = "Azure CLI is not authenticated for this profile."
            if result.timed_out:
                message = "Azure CLI authentication check timed out."
            elif result.stderr.strip():
                message = result.stderr.strip()[:600]
            return {"authenticated": False, "profile_id": profile_id, "profile": profile["name"], "error": message}
        try:
            account = _parse_json(result.stdout, "account show")
        except ValueError as exc:
            return {"authenticated": False, "profile_id": profile_id, "profile": profile["name"], "error": str(exc)}
        if not isinstance(account, dict):
            return {"authenticated": False, "profile_id": profile_id, "profile": profile["name"], "error": "Unexpected Azure account response."}
        user = account.get("user") if isinstance(account.get("user"), dict) else {}
        return {
            "authenticated": True,
            "profile_id": profile_id,
            "profile": profile["name"],
            "user": str(user.get("name", "") or ""),
            "user_type": str(user.get("type", "") or ""),
            "tenant_id": str(account.get("tenantId", "") or ""),
            "subscription_id": str(account.get("id", "") or ""),
            "subscription_name": str(account.get("name", "") or ""),
            "subscription_state": str(account.get("state", "") or ""),
            "is_default_profile": profile_id == "azure-cli-default",
            "read_only_discovery": True,
        }

    def _list_subscriptions_single(self, profile_id: str, refresh: bool = False) -> dict[str, Any]:
        profile = self.store.get_profile(profile_id)
        args = ["account", "list", "--all"]
        if refresh:
            args.append("--refresh")
        args.extend(["--output", "json"])
        try:
            result = self.runner("az", args, timeout_seconds=90 if refresh else 45, env_overrides=self._env_for(profile_id))
        except FileNotFoundError as exc:
            return {"success": False, "profile_id": profile_id, "error": str(exc), "subscriptions": []}
        if not result.succeeded:
            error = "Azure subscription discovery timed out." if result.timed_out else (result.stderr.strip() or "Azure CLI could not list subscriptions.")
            return {"success": False, "profile_id": profile_id, "error": error[:800], "subscriptions": []}
        try:
            entries = _parse_json(result.stdout, "account list")
        except ValueError as exc:
            return {"success": False, "profile_id": profile_id, "error": str(exc), "subscriptions": []}
        if not isinstance(entries, list):
            return {"success": False, "profile_id": profile_id, "error": "Unexpected Azure subscription response.", "subscriptions": []}

        safe: list[dict[str, Any]] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            user = item.get("user") if isinstance(item.get("user"), dict) else {}
            safe.append({
                "subscription_id": str(item.get("id", "") or ""),
                "name": str(item.get("name", "") or ""),
                "tenant_id": str(item.get("tenantId", "") or ""),
                "state": str(item.get("state", "") or ""),
                "is_default": bool(item.get("isDefault", False)),
                "user": str(user.get("name", "") or ""),
                "cloud_name": str(item.get("environmentName", "") or ""),
            })
        return {
            "success": True,
            "profile_id": profile_id,
            "profile": profile["name"],
            "refresh_requested": refresh,
            "count": len(safe),
            "subscriptions": safe,
            "scope": "subscriptions_cached_or_accessible_to_this_azure_cli_profile",
        }

    def _list_tenants_single(self, profile_id: str, refresh: bool = False) -> dict[str, Any]:
        subscriptions = self._list_subscriptions_single(profile_id, refresh=refresh)
        if not subscriptions.get("success"):
            return {
                "success": False,
                "profile_id": profile_id,
                "error": subscriptions.get("error", "Tenant discovery failed."),
                "tenants": [],
                "discovery_method": "subscription_tenant_ids",
            }
        tenant_ids = sorted({
            str(item.get("tenant_id"))
            for item in subscriptions["subscriptions"]
            if item.get("tenant_id")
        })
        status = self._get_auth_status_single(profile_id)
        active_tenant = status.get("tenant_id") if status.get("authenticated") else None
        if active_tenant and active_tenant not in tenant_ids:
            tenant_ids.append(active_tenant)
        return {
            "success": True,
            "profile_id": profile_id,
            "count": len(tenant_ids),
            "tenants": [{"tenant_id": tid, "has_cached_subscription": any(s.get("tenant_id") == tid for s in subscriptions["subscriptions"])} for tid in tenant_ids],
            "discovery_method": "deduplicated_tenant_ids_from_azure_cli_account_cache",
            "limitation": "This reports tenants represented in the selected Azure CLI profile. It does not enumerate every directory the user may be invited to unless Azure CLI has been authenticated to those tenants.",
        }
