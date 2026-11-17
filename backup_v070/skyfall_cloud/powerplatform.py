"""Read-only Power Platform CLI profile and environment discovery."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from .command_runner import CommandResult, run_cli

Runner = Callable[..., CommandResult]


def parse_pac_auth_profiles(text: str) -> list[dict[str, Any]]:
    """Best-effort parser for the documented `pac auth list` aligned table.

    The CLI currently emits a human-readable table rather than a documented
    JSON output mode for this command. Parsing is intentionally conservative.
    """
    profiles: list[dict[str, Any]] = []
    row_pattern = re.compile(r"^\s*\[(?P<index>\d+)\]\s+(?P<active>\*)?\s*(?P<kind>[A-Za-z0-9_-]+)\s+(?P<rest>.*)$")
    url_pattern = re.compile(r"https?://[^\s]+", re.IGNORECASE)
    email_pattern = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

    for line in (text or "").splitlines():
        match = row_pattern.match(line)
        if not match:
            continue
        rest = match.group("rest").strip()
        url_match = url_pattern.search(rest)
        url = url_match.group(0).rstrip("/]") if url_match else ""
        label = rest[:url_match.start()].strip() if url_match else rest
        user_match = email_pattern.search(rest[url_match.end():] if url_match else rest)
        user = user_match.group(0) if user_match else ""
        # Do not infer missing fields from potentially misaligned table output.
        profiles.append({
            "index": int(match.group("index")),
            "active": bool(match.group("active")),
            "kind": match.group("kind"),
            "label": re.sub(r"\s+", " ", label),
            "environment_url": url,
            "user": user,
            "parse_quality": "best_effort_table_parse",
        })
    return profiles


def _decode_json_output(text: str) -> Any:
    clean = (text or "").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        # Some CLI builds may print a short preamble before JSON. Decode the
        # first JSON value without returning the preamble to model context.
        decoder = json.JSONDecoder()
        for index, char in enumerate(clean):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(clean[index:])
                return value
            except json.JSONDecodeError:
                continue
        raise ValueError("PAC CLI did not return valid JSON for environment discovery.")


class PowerPlatformDiscovery:
    def __init__(self, runner: Runner = run_cli) -> None:
        self.runner = runner

    def list_auth_profiles(self) -> dict[str, Any]:
        try:
            result = self.runner("pac", ["auth", "list"], timeout_seconds=30)
        except FileNotFoundError as exc:
            return {"success": False, "error": str(exc), "profiles": []}
        if not result.succeeded:
            error = "PAC CLI profile discovery timed out." if result.timed_out else (result.stderr.strip() or "PAC CLI could not list authentication profiles.")
            return {"success": False, "error": error[:800], "profiles": []}
        profiles = parse_pac_auth_profiles(result.stdout)
        return {
            "success": True,
            "count": len(profiles),
            "profiles": profiles,
            "active_profile_index": next((p["index"] for p in profiles if p["active"]), None),
            "parser_status": "parsed" if profiles else "no_profiles_or_unrecognized_output",
            "scope": "profiles_registered_in_the_current_pac_cli_installation",
        }

    def get_auth_status(self) -> dict[str, Any]:
        profiles_result = self.list_auth_profiles()
        if not profiles_result.get("success"):
            return profiles_result
        active = next((p for p in profiles_result["profiles"] if p["active"]), None)
        return {
            "authenticated": active is not None,
            "active_profile": active,
            "profile_count": profiles_result.get("count", 0),
            "message": "Active PAC CLI profile detected." if active else "No active PAC CLI authentication profile was detected.",
            "limitations": [
                "PAC CLI profile selection is global to the PAC CLI installation.",
                "SKYFALL does not change the active PAC profile automatically in v0.7.",
            ],
        }

    def list_environments(self) -> dict[str, Any]:
        profiles_result = self.list_auth_profiles()
        if not profiles_result.get("success"):
            return {"success": False, "error": profiles_result.get("error"), "environments": []}
        active = next((p for p in profiles_result["profiles"] if p["active"]), None)
        if not active:
            return {
                "success": False,
                "error": "No active PAC CLI authentication profile. Sign in with `pac auth create`, then retry.",
                "environments": [],
            }
        try:
            result = self.runner("pac", ["admin", "list", "--json"], timeout_seconds=60)
        except FileNotFoundError as exc:
            return {"success": False, "error": str(exc), "environments": []}
        if not result.succeeded:
            error = "PAC CLI environment discovery timed out." if result.timed_out else (result.stderr.strip() or "PAC CLI could not list tenant environments. The active user may not have the required Power Platform administrative role.")
            return {
                "success": False,
                "error": error[:1000],
                "environments": [],
                "active_profile": active,
                "required_access": "Power Platform tenant administrative permissions may be required by pac admin list.",
            }
        try:
            raw = _decode_json_output(result.stdout)
        except ValueError as exc:
            return {"success": False, "error": str(exc), "environments": [], "active_profile": active}
        if isinstance(raw, dict):
            raw_items = raw.get("value") or raw.get("environments") or raw.get("EnvironmentList") or []
        else:
            raw_items = raw
        if not isinstance(raw_items, list):
            return {"success": False, "error": "Unexpected PAC CLI environment response format.", "environments": [], "active_profile": active}

        safe: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            # Allow only non-secret environment metadata fields.
            def first(*keys: str) -> str:
                for key in keys:
                    value = item.get(key)
                    if value is not None and str(value).strip():
                        return str(value)
                return ""
            safe.append({
                "name": first("DisplayName", "displayName", "Name", "name"),
                "environment_id": first("EnvironmentId", "environmentId", "id"),
                "environment_url": first("EnvironmentUrl", "environmentUrl", "Url", "url"),
                "type": first("EnvironmentType", "environmentType", "Type", "type"),
                "organization_id": first("OrganizationId", "organizationId", "Organization Id"),
                "region": first("Region", "region", "Geo", "geo"),
                "state": first("State", "state", "RuntimeState", "runtimeState"),
            })
        return {
            "success": True,
            "count": len(safe),
            "active_profile": active,
            "environments": safe,
            "scope": "tenant_environments_visible_to_pac_admin_list_for_the_active_profile",
            "limitations": [
                "Environment enumeration uses the currently active PAC CLI profile only.",
                "The PAC CLI profile is not switched automatically by SKYFALL.",
                "Tenant-wide environment enumeration may require Power Platform administrative permissions.",
            ],
        }
