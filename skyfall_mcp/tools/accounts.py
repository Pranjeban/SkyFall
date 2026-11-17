"""Read-only MCP tools for Microsoft account and environment discovery."""

from __future__ import annotations

import json
import os
from typing import Any

from skyfall_cloud.azure_profiles import AzureProfileManager
from skyfall_cloud.powerplatform_accounts import PowerPlatformAccountStore, PowerPlatformApi
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


def start_azure_login(profile_name: str = "", tenant_id: str = "", profile_id: str = "") -> str:
    """Start Azure CLI browser sign-in in a named SKYFALL-isolated profile."""
    clean_name = (profile_name or "").strip()
    clean_tenant = (tenant_id or "").strip()
    clean_profile_id = (profile_id or "").strip()
    profile: dict[str, Any] = {}

    if not clean_profile_id and (not clean_name or not clean_tenant):
        required = []
        if not clean_name:
            required.append("profile_name")
        if not clean_tenant:
            required.append("tenant_id")
        return _json({
            "success": False,
            "requires_input": required,
            "message": "Provide a profile name and tenant GUID or domain for a new Azure account.",
            "login_started": False,
        })

    if os.environ.get("SKYFALL_TEST_MODE") == "1":
        return _json({
            "success": False,
            "status": "blocked_test_mode",
            "error": "External Azure sign-in is disabled in SKYFALL_TEST_MODE.",
            "login_started": False,
        })

    manager = AzureProfileManager()
    if clean_profile_id:
        try:
            profile = manager.store.get_profile(clean_profile_id)
            if profile.get("profile_id") == "azure-cli-default":
                return _json({
                    "success": False,
                    "error": "Sign-in through the default Azure CLI profile is disabled to protect its existing context. Create a named SKYFALL profile instead.",
                    "login_started": False,
                })
            if clean_tenant:
                profile = manager.store.update_tenant_hint(clean_profile_id, clean_tenant)
        except (KeyError, ValueError) as exc:
            return _json({"success": False, "error": str(exc), "login_started": False})
    def sign_in() -> dict[str, Any]:
        selected_profile_id = clean_profile_id
        if not selected_profile_id:
            profile = manager.store.create_profile(clean_name, clean_tenant)
            selected_profile_id = str(profile["profile_id"])
        result = manager.login_profile(selected_profile_id)
        if result.get("success"):
            profiles = manager.store.list_profiles()
            result["profiles"] = {
                "count": len(profiles),
                "profiles": profiles,
            }
        return result

    job = AUTH_JOBS.start(
        f"Azure sign-in: {clean_name or clean_profile_id}",
        sign_in,
    )
    return _json({
        "success": True,
        "login_started": True,
        **job,
        "profile_name": clean_name or profile.get("name", ""),
        "profile_id": clean_profile_id or None,
        "tenant_id": clean_tenant or profile.get("tenant_hint", ""),
        "next_step": "Complete the Microsoft browser sign-in. Then call get_microsoft_auth_job_status with the returned job_id to view authentication and subscription discovery results.",
        "credential_material_returned": False,
    })


def configure_powerplatform_app(client_id: str) -> str:
    """Save a public Microsoft Entra desktop app ID; no secret is accepted or stored."""
    try:
        PowerPlatformAccountStore().set_client_id(client_id)
    except ValueError as exc:
        return _json({"success": False, "error": str(exc)})
    return _json({"success": True, "configured": True, "credential_material_returned": False})


def list_powerplatform_auth_profiles() -> str:
    """List SKYFALL-local Microsoft OAuth account profiles without credentials."""
    store = PowerPlatformAccountStore()
    profiles = store.list_profiles()
    active_id = store.get_active_profile_id()
    return _json({
        "success": True,
        "count": len(profiles),
        "profiles": [{**item, "active": item.get("profile_id") == active_id} for item in profiles],
        "client_id_configured": bool(store.get_client_id()),
        "credential_material_returned": False,
    })


def get_powerplatform_auth_status() -> str:
    """Report selected SKYFALL Power Platform OAuth profile status."""
    store = PowerPlatformAccountStore()
    active = store.get_profile(store.get_active_profile_id())
    return _json({
        "authenticated": active is not None,
        "active_profile": active,
        "profile_count": len(store.list_profiles()),
        "client_id_configured": bool(store.get_client_id()),
        "credential_material_returned": False,
    })


def list_powerplatform_environments() -> str:
    """List environments available to the selected saved Microsoft OAuth profile."""
    return _json(PowerPlatformApi().list_environments())


def start_powerplatform_login(profile_name: str, tenant: str = "organizations") -> str:
    """Start browser-based MSAL sign-in and save a named SKYFALL-local profile."""
    name = (profile_name or "").strip()
    if not name:
        return _json({"success": False, "requires_input": ["profile_name"], "message": "Provide a name for the Microsoft account profile."})
    store = PowerPlatformAccountStore()
    if not store.get_client_id():
        return _json({"success": False, "requires_input": ["client_id"], "message": "Configure the Microsoft Entra desktop app client ID with configure_powerplatform_app, then start sign-in."})

    def sign_in() -> dict[str, Any]:
        api = PowerPlatformApi(store)
        result = api.add_account(name, tenant or "organizations")
        result["environments"] = api.list_environments()
        profiles = store.list_profiles()
        active_id = store.get_active_profile_id()
        result["profiles"] = {
            "count": len(profiles),
            "profiles": [{**item, "active": item.get("profile_id") == active_id} for item in profiles],
        }
        return result

    job = AUTH_JOBS.start(f"Power Platform sign-in: {name}", sign_in)
    return _json({
        "success": True,
        "login_started": True,
        **job,
        "profile_name": name,
        "tenant": tenant or "organizations",
        "next_step": "Complete the Microsoft browser sign-in. Then call get_microsoft_auth_job_status with the returned job_id to view saved profile and environment results.",
        "credential_material_returned": False,
    })


def get_microsoft_auth_job_status(job_id: str) -> str:
    """Get progress and safe discovery results for a Microsoft sign-in job."""
    return _json(AUTH_JOBS.get(job_id))
