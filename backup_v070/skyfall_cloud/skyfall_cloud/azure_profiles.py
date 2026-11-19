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
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .command_runner import CommandResult, redact_sensitive_text, run_cli


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


def _validate_tenant_identifier(value: str) -> str:
    """Accept a tenant GUID or a DNS-style verified tenant domain."""
    tenant = (value or "").strip()
    if not tenant or len(tenant) > 200:
        raise ValueError("Enter a tenant ID or tenant domain to create an Azure profile.")
    if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", tenant):
        return tenant
    if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", tenant) and "." in tenant:
        return tenant
    raise ValueError("Tenant must be a GUID or a tenant domain such as contoso.onmicrosoft.com.")




def _is_azure_not_authenticated_error(value: str) -> bool:
    text = (value or "").casefold()
    patterns = (
        "please run 'az login'",
        'please run "az login"',
        "run az login to",
        "not logged in",
        "not authenticated",
        "no subscription found. please run az login",
    )
    return any(pattern in text for pattern in patterns)


def _friendly_azure_cli_error(value: str, fallback: str) -> str:
    if _is_azure_not_authenticated_error(value):
        return "This Azure profile is not signed in. Create or select a SKYFALL profile and choose Sign in to open Microsoft authentication."
    return (value or fallback).strip()[:800]


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

    def create_profile(
        self, name: str, tenant_hint: str, *, allow_tenant_discovery: bool = False
    ) -> dict[str, Any]:
        clean_name = (name or "").strip()
        if not clean_name or len(clean_name) > 80:
            raise ValueError("Profile name must contain 1 to 80 characters.")
        tenant = (
            _validate_tenant_identifier(tenant_hint)
            if (tenant_hint or "").strip()
            else "" if allow_tenant_discovery else _validate_tenant_identifier("")
        )

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
        return profile

    def update_tenant_hint(self, profile_id: str, tenant_hint: str) -> dict[str, Any]:
        """Set the required tenant hint on an existing isolated profile."""
        profile = self.get_profile(profile_id)
        if profile["profile_id"] == "azure-cli-default":
            raise ValueError("The Default Azure CLI profile is read-only. Create a named SKYFALL profile instead.")
        tenant = _validate_tenant_identifier(tenant_hint)
        data = self._read()
        for item in data["profiles"]:
            if item.get("profile_id") == profile_id:
                item["tenant_hint"] = tenant
                self._write(data)
                return self.get_profile(profile_id)
        raise KeyError(f"Unknown Azure profile: {profile_id}")

    def delete_profile(self, profile_id: str) -> None:
        """Delete an isolated SKYFALL profile and its local Azure CLI token cache."""
        profile = self.get_profile(profile_id)
        if profile["profile_id"] == "azure-cli-default":
            raise ValueError("The Default Azure CLI profile cannot be deleted by SKYFALL.")
        config_dir = Path(profile["config_dir"]).resolve()
        root = self.root.resolve()
        if not config_dir.is_relative_to(root) or config_dir == root:
            raise ValueError("Refusing to delete a profile directory outside SKYFALL's managed profile root.")
        data = self._read()
        data["profiles"] = [p for p in data["profiles"] if p.get("profile_id") != profile_id]
        self._write(data)
        shutil.rmtree(config_dir.parent, ignore_errors=True)

    @staticmethod
    def login_command(profile: dict[str, Any]) -> str:
        config_dir = str(profile.get("config_dir", ""))
        # PowerShell single-quoted string escaping.
        escaped_path = config_dir.replace("'", "''")
        command = (
            f"$env:AZURE_CONFIG_DIR = '{escaped_path}'`n"
            "az config set core.enable_broker_on_windows=false`n"
            "az config set core.login_experience_v2=off`n"
            "az login --allow-no-subscriptions"
        )
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

    def get_access_token(self, profile_id: str, resource: str) -> str:
        """Get a short-lived resource token from the selected isolated Azure CLI profile.

        The token is returned only to the in-process API caller and is never
        included in command output, logs, or profile metadata.
        """
        target = (resource or "").strip()
        parsed = urlparse(target)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or parsed.username or parsed.password or not (
            host in {"api.powerplatform.com", "service.powerapps.com"}
            or host.endswith(".dynamics.com")
        ):
            raise ValueError("Token requests are limited to the Power Platform API and Dataverse environment hosts.")
        if os.environ.get("SKYFALL_TEST_MODE") == "1":
            raise RuntimeError("External Azure CLI token requests are disabled in SKYFALL_TEST_MODE.")
        profile = self.store.get_profile(profile_id)
        executable = shutil.which("az")
        if not executable:
            raise FileNotFoundError("Azure CLI (az) is required for Power Platform sign-in.")
        arguments = [executable, "account", "get-access-token", "--resource", target, "--output", "json", "--only-show-errors"]
        tenant = str(profile.get("tenant_hint") or "").strip()
        if tenant:
            arguments.extend(["--tenant", tenant])
        environment = os.environ.copy()
        environment.update({key: value for key, value in self._env_for(profile_id).items() if value is not None})
        try:
            completed = subprocess.run(
                arguments,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
                env=environment,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Azure CLI token request timed out. Sign in again and retry.") from exc
        if completed.returncode != 0:
            detail = redact_sensitive_text(completed.stderr or "").strip()
            raise RuntimeError(detail[:700] or "Azure CLI could not get a token for this Power Platform resource.")
        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("Azure CLI returned an unreadable token response.") from exc
        token = str(payload.get("accessToken") or "").strip() if isinstance(payload, dict) else ""
        if not token:
            raise RuntimeError("Azure CLI did not return a Power Platform access token. Sign in again and retry.")
        return token

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

    def login_profile(self, profile_id: str) -> dict[str, Any]:
        """Open browser-based Microsoft sign-in in the selected isolated profile.

        WAM and the interactive subscription selector are disabled only inside
        this profile's AZURE_CONFIG_DIR. The user's default Azure CLI context
        and its settings are not changed.
        """
        profile = self.store.get_profile(profile_id)
        if profile["profile_id"] == "azure-cli-default":
            raise ValueError(
                "SKYFALL does not sign in through the Default Azure CLI profile because that would alter your existing Azure CLI context. "
                "Create a named SKYFALL profile with a tenant ID or domain instead."
            )
        tenant = str(profile.get("tenant_hint") or "").strip()
        env = self._env_for(profile_id)

        # Force the standard browser flow for this isolated profile, without
        # changing the user's global Azure CLI configuration.
        for setting in (
            "core.enable_broker_on_windows=false",
            "core.login_experience_v2=off",
        ):
            configured = self.runner(
                "az", ["config", "set", setting, "--only-show-errors"],
                timeout_seconds=30, env_overrides=env,
            )
            if not configured.succeeded:
                detail = configured.stderr.strip() or configured.stdout.strip()
                return {
                    "success": False,
                    "profile_id": profile_id,
                    "profile": profile["name"],
                    "error": (detail or f"Could not configure isolated browser sign-in ({setting}).")[:800],
                }

        login_arguments = ["login", "--allow-no-subscriptions", "--output", "json", "--only-show-errors"]
        if tenant:
            login_arguments.extend(["--tenant", tenant])
        login = self.runner(
            "az",
            login_arguments,
            timeout_seconds=300,
            env_overrides=env,
        )
        if not login.succeeded:
            if login.timed_out:
                error = "Microsoft sign-in timed out. Complete the browser sign-in and try again."
            else:
                error = login.stderr.strip() or login.stdout.strip() or "Azure sign-in did not complete."
            return {
                "success": False,
                "profile_id": profile_id,
                "profile": profile["name"],
                "tenant_hint": tenant,
                "error": error[:1000],
            }

        # Authentication succeeded. Discover all permitted data immediately.
        auth = self.get_auth_status(profile_id)
        subscriptions = self.list_subscriptions(profile_id, refresh=True)
        tenants = self.list_tenants(profile_id, refresh=False)
        return {
            "success": True,
            "profile_id": profile_id,
            "profile": profile["name"],
            "tenant_hint": tenant,
            "auth": auth,
            "subscriptions": subscriptions,
            "tenants": tenants,
            "message": "Microsoft sign-in completed. Subscription and tenant discovery has run automatically.",
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
                message = _friendly_azure_cli_error(
                    result.stderr,
                    "Azure CLI could not verify this profile.",
                )[:600]
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
            error = (
                "Azure subscription discovery timed out."
                if result.timed_out
                else _friendly_azure_cli_error(result.stderr, "Azure CLI could not list subscriptions.")
            )
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
                "profile": profile["name"],
                "profile_id": profile_id,
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
        tenant_ids = {
            str(item.get("tenant_id"))
            for item in subscriptions["subscriptions"]
            if item.get("tenant_id")
        }
        configured_tenant = str(self.store.get_profile(profile_id).get("tenant_hint") or "").strip()
        status = self._get_auth_status_single(profile_id)
        active_tenant = str(status.get("tenant_id") or "") if status.get("authenticated") else ""
        if active_tenant:
            tenant_ids.add(active_tenant)
        # A configured tenant domain is an input alias, not a tenant ID. Once
        # Azure CLI returns the canonical tenant GUID, do not display the
        # domain as a second, duplicate tenant entry. If no canonical ID is
        # available yet and the configured value is a GUID, it is safe to use.
        if not tenant_ids and configured_tenant and re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            configured_tenant,
        ):
            tenant_ids.add(configured_tenant)
        return {
            "success": True,
            "profile_id": profile_id,
            "count": len(tenant_ids),
            "tenants": [{
                "tenant_id": tid,
                "has_cached_subscription": any(s.get("tenant_id") == tid for s in subscriptions["subscriptions"]),
                "is_configured_tenant": bool(configured_tenant and (configured_tenant.casefold() == tid.casefold())),
            } for tid in sorted(tenant_ids)],
            "configured_tenant_hint": configured_tenant or None,
            "discovery_method": "canonical_tenant_ids_from_azure_cli_subscription_and_account_metadata",
            "limitation": "This reports canonical tenant IDs represented in the selected Azure CLI profile. A configured tenant domain is retained as a sign-in hint and is not shown as a separate tenant ID. It does not enumerate every directory the user may be invited to unless Azure CLI has been authenticated to those tenants.",
        }
