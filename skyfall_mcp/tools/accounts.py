"""Read-only MCP tools for Microsoft account and environment discovery."""

from __future__ import annotations

import json
from typing import Any

from skyfall_cloud.azure_profiles import AzureProfileManager
from skyfall_cloud.powerplatform import PowerPlatformDiscovery
from skyfall_cloud.auth_jobs import AUTH_JOBS


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def list_azure_profiles() -> str:
    """List SKYFALL Azure CLI profile metadata. Never returns credential material."""
    manager = AzureProfileManager()
    profiles = manager.store.list_profiles()
    safe = [
        {
            "profile_id": p["profile_id"],
            "name": p["name"],
            "kind": p["kind"],
            "tenant_hint": p.get("tenant_hint"),
            "created_at": p.get("created_at"),
        }
        for p in profiles
    ]
    return _json({"count": len(safe), "profiles": safe, "credential_material_returned": False})


def get_azure_auth_status(profile_id: str = "all") -> str:
    """Check one Azure CLI profile or all registered profiles for sign-in status."""
    return _json(AzureProfileManager().get_auth_status(profile_id))


def list_azure_subscriptions(profile_id: str = "all", refresh: bool = False) -> str:
    """List subscriptions across all registered Azure CLI profiles by default, or one specified profile; optionally refresh from Azure."""
    return _json(AzureProfileManager().list_subscriptions(profile_id, refresh=refresh))


def list_azure_tenants(profile_id: str = "all", refresh: bool = False) -> str:
    """List tenant IDs represented across all registered profiles by default, or one selected profile."""
    return _json(AzureProfileManager().list_tenants(profile_id, refresh=refresh))


def list_powerplatform_auth_profiles() -> str:
    """List PAC CLI authentication profiles without changing the active profile."""
    return _json(PowerPlatformDiscovery().list_auth_profiles())


def get_powerplatform_auth_status() -> str:
    """Report the currently active PAC CLI profile, if one exists."""
    return _json(PowerPlatformDiscovery().get_auth_status())


def list_powerplatform_environments() -> str:
    """List tenant environments visible to pac admin list for the currently active PAC profile."""
    return _json(PowerPlatformDiscovery().list_environments())


def start_azure_login(
    profile_name: str = "",
    tenant_id: str = "",
    profile_id: str = "",
) -> str:
    """Start browser-based Azure sign-in for a named SKYFALL profile.

    Create a new profile by supplying profile_name and tenant_id, or sign in
    to an existing isolated profile by supplying profile_id. The browser login
    runs asynchronously; use get_microsoft_auth_job_status after the user
    completes sign-in to retrieve discovered tenants and subscriptions.
    """
    manager = AzureProfileManager()
    if profile_id.strip():
        profile = manager.store.get_profile(profile_id)
        if tenant_id.strip():
            profile = manager.store.update_tenant_hint(profile_id, tenant_id)
        elif not profile.get("tenant_hint"):
            return _json({
                "success": False,
                "requires_input": ["tenant_id"],
                "profile_id": profile_id,
                "message": "This profile needs a tenant ID or verified tenant domain before sign-in.",
            })
    else:
        if not (profile_name or "").strip() or not (tenant_id or "").strip():
            missing = []
            if not (profile_name or "").strip():
                missing.append("profile_name")
            if not (tenant_id or "").strip():
                missing.append("tenant_id")
            return _json({
                "success": False,
                "requires_input": missing,
                "message": "Provide a profile name and tenant ID or verified tenant domain before Azure sign-in.",
            })
        profile = manager.store.create_profile(profile_name, tenant_id)

    job = AUTH_JOBS.start(
        f"Azure sign-in: {profile['name']}",
        lambda: manager.login_profile(profile["profile_id"]),
    )
    return _json({
        "success": True,
        "login_started": True,
        **job,
        "profile_id": profile["profile_id"],
        "profile_name": profile["name"],
        "tenant": profile.get("tenant_hint"),
        "next_step": "A Microsoft sign-in page should open. Complete sign-in, then call get_microsoft_auth_job_status with the returned job_id to retrieve tenants and subscriptions.",
        "credential_material_returned": False,
    })


def start_powerplatform_login(
    profile_name: str,
    environment: str = "",
    confirm_global_profile_activation: bool = False,
) -> str:
    """Start PAC CLI sign-in only after acknowledging its global profile side effect.

    PAC CLI auth profiles are stored by the local PAC CLI installation, and a
    newly created profile may become its active profile. SKYFALL therefore
    requires an explicit confirmation before starting this operation from Chat.
    """
    name = (profile_name or "").strip()
    if not name:
        return _json({"success": False, "requires_input": ["profile_name"], "message": "Provide a Power Platform profile name."})
    if len(name) > 30:
        return _json({"success": False, "requires_input": [], "error": "Power Platform profile names must contain 1 to 30 characters."})
    if not confirm_global_profile_activation:
        return _json({
            "success": False,
            "requires_confirmation": True,
            "confirmation_key": "confirm_global_profile_activation",
            "profile_name": name,
            "environment": (environment or "").strip() or None,
            "warning": (
                "Creating a PAC CLI authentication profile may make it the globally active profile "
                "for this local PAC CLI installation. This can affect other terminals, projects and "
                "Power Platform CLI commands. No profile has been created and no sign-in has started."
            ),
            "next_step": "Explain this impact and ask the user to explicitly confirm. Only after a clear yes, call this tool again with confirm_global_profile_activation=true.",
        })
    discovery = PowerPlatformDiscovery()
    job = AUTH_JOBS.start(
        f"Power Platform sign-in: {name}",
        lambda: discovery.create_profile_and_login(name, environment),
    )
    return _json({
        "success": True,
        "login_started": True,
        **job,
        "profile_name": name,
        "environment": (environment or "").strip() or None,
        "tenant_resolution": "The tenant is determined by the Microsoft account selected during delegated PAC CLI sign-in; the PAC CLI user flow does not accept a tenant argument.",
        "next_step": "Complete the Microsoft sign-in page, then call get_microsoft_auth_job_status with the returned job_id to retrieve the profile and accessible environments.",
        "credential_material_returned": False,
    })


def get_microsoft_auth_job_status(job_id: str) -> str:
    """Get progress and safe discovery results for a Microsoft sign-in job."""
    return _json(AUTH_JOBS.get(job_id))
