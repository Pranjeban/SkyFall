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


_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _clean_cli_output(text: str) -> str:
    """Remove terminal decoration and UTF-8 BOM without changing data values."""
    return _ANSI_ESCAPE.sub("", (text or "").replace("\ufeff", "")).strip()


def _decode_json_output(text: str) -> Any:
    """Decode a JSON value even when PAC emits a preamble or ANSI decoration."""
    clean = _clean_cli_output(text)
    if not clean:
        raise ValueError("PAC CLI returned no environment data.")
    try:
        value = json.loads(clean)
        if isinstance(value, (dict, list)):
            return value
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(clean):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(clean[index:])
            if isinstance(value, (dict, list)):
                return value
        except json.JSONDecodeError:
            continue
    raise ValueError("PAC CLI did not return JSON environment data.")


def parse_pac_admin_environment_table(text: str) -> list[dict[str, str]]:
    """Parse the documented human-readable `pac admin list` table.

    Column boundaries are derived from the header and then applied as fixed
    slices. This preserves environment names that contain spaces.
    """
    lines = [_ANSI_ESCAPE.sub("", line).rstrip("\r") for line in (text or "").replace("\ufeff", "").splitlines()]
    header_index = -1
    starts: list[int] = []
    labels = ["Environment", "Environment Id", "Environment Url", "Type", "Organization Id"]

    for index, line in enumerate(lines):
        folded = line.casefold()
        positions: list[int] = []
        cursor = 0
        found = True
        for label in labels:
            position = folded.find(label.casefold(), cursor)
            if position < 0:
                found = False
                break
            positions.append(position)
            cursor = position + len(label)
        if found:
            header_index = index
            starts = positions
            break

    if header_index < 0:
        return []

    rows: list[dict[str, str]] = []
    for line in lines[header_index + 1:]:
        if not line.strip():
            continue
        if re.fullmatch(r"[\s|+\-=]+", line):
            continue
        # PAC tables are aligned to the header. Slicing avoids splitting a
        # display name such as "Contoso Developer Environment".
        padded = line + (" " * max(0, starts[-1] + 80 - len(line)))
        values = [
            padded[starts[i]:starts[i + 1]].strip()
            for i in range(len(starts) - 1)
        ]
        values.append(padded[starts[-1]:].strip())
        if len(values) < 5:
            continue
        name, environment_id, environment_url, environment_type, organization_id = values[:5]
        # Ignore non-record footer/help lines. A valid row must provide at
        # least an environment ID or an HTTPS environment URL.
        if not name or not (environment_id or re.match(r"https?://", environment_url, re.I)):
            continue
        rows.append({
            "name": name,
            "environment_id": environment_id,
            "environment_url": environment_url,
            "type": environment_type,
            "organization_id": organization_id,
            "region": "",
            "tenant_id": "",
            "state": "",
        })
    return rows


def _normalize_environment_json(raw: Any) -> list[dict[str, str]] | None:
    """Normalize documented and commonly returned PAC JSON envelopes."""
    if isinstance(raw, list):
        raw_items = raw
    elif isinstance(raw, dict):
        key_map = {str(key).casefold(): key for key in raw}
        raw_items = None
        for candidate in ("value", "environments", "environmentlist", "items", "data", "results"):
            actual = key_map.get(candidate)
            value = raw.get(actual) if actual is not None else None
            if isinstance(value, list):
                raw_items = value
                break
        if raw_items is None and any(key in key_map for key in ("environmentid", "id", "displayname", "name")):
            raw_items = [raw]
        if raw_items is None:
            return None
    else:
        return None

    safe: list[dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        folded = {str(key).casefold(): value for key, value in item.items()}

        def first(*keys: str) -> str:
            for key in keys:
                value = folded.get(key.casefold())
                if value is not None and str(value).strip():
                    return str(value).strip()
            return ""

        safe.append({
            "name": first("DisplayName", "Name", "FriendlyName"),
            "environment_id": first("EnvironmentId", "Id", "Environment ID"),
            "environment_url": first("EnvironmentUrl", "Url", "Environment URL"),
            "type": first("EnvironmentType", "Type"),
            "organization_id": first("OrganizationId", "Organization ID"),
            "region": first("Region", "Geo"),
            "tenant_id": first("TenantId", "Tenant ID"),
            "state": first("State", "RuntimeState"),
        })
    return safe


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
                "SKYFALL does not change the active PAC profile automatically in v0.9.1.",
            ],
        }

    def create_profile_and_login(
        self,
        profile_name: str,
        environment: str | None = None,
    ) -> dict[str, Any]:
        """Create a named PAC profile using PAC CLI's interactive sign-in.

        For delegated user authentication, PAC CLI chooses the tenant from the
        Microsoft account used in the sign-in flow. Its documented --tenant
        parameter is for service-principal authentication, not this flow.
        """
        name = (profile_name or "").strip()
        if not name or len(name) > 30:
            raise ValueError("Power Platform profile names must contain 1 to 30 characters.")
        target = (environment or "").strip()
        if len(target) > 300 or any(ch in target for ch in "\r\n\x00"):
            raise ValueError("Environment name, URL or ID is invalid.")

        existing = self.list_auth_profiles()
        if existing.get("success"):
            for item in existing.get("profiles", []):
                if str(item.get("label", "")).casefold() == name.casefold():
                    raise ValueError(f"A PAC CLI profile named '{name}' already exists.")

        args = ["auth", "create", "--name", name]
        if target:
            args.extend(["--environment", target])
        # Deliberately omit --deviceCode: on an interactive Windows desktop,
        # PAC CLI uses its normal Microsoft sign-in experience.
        try:
            result = self.runner("pac", args, timeout_seconds=300)
        except FileNotFoundError as exc:
            return {"success": False, "error": str(exc), "profiles": [], "environments": []}
        if not result.succeeded:
            error = "Power Platform sign-in timed out." if result.timed_out else (
                result.stderr.strip() or result.stdout.strip() or "PAC CLI sign-in did not complete."
            )
            return {"success": False, "error": error[:1000], "profiles": [], "environments": []}

        profiles = self.list_auth_profiles()
        auth = self.get_auth_status()
        environments = self.list_environments() if auth.get("authenticated") else {
            "success": False,
            "error": "PAC CLI sign-in returned, but no active profile could be verified.",
            "environments": [],
        }
        return {
            "success": bool(profiles.get("success") and auth.get("authenticated")),
            "profile_name": name,
            "profiles": profiles,
            "auth": auth,
            "environments": environments,
            "message": "Power Platform sign-in completed. Profile and environment discovery ran automatically.",
            "tenant_resolution": "The tenant is determined by the Microsoft account used during delegated interactive sign-in.",
            "credential_material_returned": False,
        }

    def select_profile(self, index: int) -> dict[str, Any]:
        """Select a PAC profile after the UI explicitly warns about global scope."""
        if not isinstance(index, int) or index < 1:
            raise ValueError("PAC profile index must be a positive integer.")
        result = self.runner("pac", ["auth", "select", "--index", str(index)], timeout_seconds=30)
        if not result.succeeded:
            error = result.stderr.strip() or result.stdout.strip() or "PAC CLI could not select the requested profile."
            return {"success": False, "error": error[:800]}
        return {
            "success": True,
            "selected_index": index,
            "auth": self.get_auth_status(),
            "profiles": self.list_auth_profiles(),
            "environments": self.list_environments(),
            "warning": "PAC CLI profile selection is global to the local PAC CLI installation.",
        }

    def list_environments(self) -> dict[str, Any]:
        """Discover environments, preferring JSON and falling back to PAC's table output."""
        profiles_result = self.list_auth_profiles()
        if not profiles_result.get("success"):
            return {"success": False, "error": profiles_result.get("error"), "environments": []}
        active = next((p for p in profiles_result["profiles"] if p["active"]), None)
        if not active:
            return {
                "success": False,
                "error": "No active PAC CLI authentication profile was found. Connect a Power Platform account first.",
                "environments": [],
            }

        try:
            json_result = self.runner("pac", ["admin", "list", "--json"], timeout_seconds=60)
        except FileNotFoundError:
            return {"success": False, "error": "Power Platform CLI (pac) was not found on PATH.", "environments": [], "active_profile": active}

        if json_result.timed_out:
            return {
                "success": False,
                "error": "Power Platform environment discovery timed out. Check PAC CLI responsiveness and try again.",
                "environments": [],
                "active_profile": active,
                "diagnostic_code": "environment_discovery_timeout",
            }

        json_error = "PAC CLI JSON output was unavailable."
        if json_result.succeeded:
            combined_output = "\n".join(part for part in (json_result.stdout, json_result.stderr) if part)
            try:
                raw = _decode_json_output(combined_output)
                safe = _normalize_environment_json(raw)
                if safe is not None:
                    return {
                        "success": True,
                        "count": len(safe),
                        "active_profile": active,
                        "environments": safe,
                        "discovery_format": "json",
                        "scope": "tenant_environments_visible_to_pac_admin_list_for_the_active_profile",
                        "limitations": [
                            "Environment enumeration uses the currently active PAC CLI profile only.",
                            "PAC CLI profile selection is global to the local PAC CLI installation.",
                            "Tenant-wide environment enumeration may require Power Platform administrative permissions.",
                        ],
                    }
                json_error = "PAC CLI JSON was valid but did not contain a recognized environment list."
            except ValueError as exc:
                json_error = str(exc)
        else:
            json_error = "PAC CLI JSON mode was not available for this command."

        # PAC CLI also documents a human-readable table form for `pac admin list`.
        # Retry that form rather than making environment discovery depend on JSON.
        try:
            table_result = self.runner("pac", ["admin", "list"], timeout_seconds=60)
        except FileNotFoundError:
            return {"success": False, "error": "Power Platform CLI (pac) was not found on PATH.", "environments": [], "active_profile": active}

        if table_result.timed_out:
            return {
                "success": False,
                "error": "Power Platform environment discovery timed out while reading the standard environment list.",
                "environments": [],
                "active_profile": active,
                "diagnostic_code": "environment_table_timeout",
            }

        table_output = "\n".join(part for part in (table_result.stdout, table_result.stderr) if part)
        table_environments = parse_pac_admin_environment_table(table_output) if table_result.succeeded else []
        if table_result.succeeded and table_environments:
            return {
                "success": True,
                "count": len(table_environments),
                "active_profile": active,
                "environments": table_environments,
                "discovery_format": "table_fallback",
                "notice": "PAC CLI returned the standard table format; SKYFALL parsed its environment metadata successfully.",
                "scope": "tenant_environments_visible_to_pac_admin_list_for_the_active_profile",
                "limitations": [
                    "Environment enumeration uses the currently active PAC CLI profile only.",
                    "PAC CLI profile selection is global to the local PAC CLI installation.",
                    "Tenant-wide environment enumeration may require Power Platform administrative permissions.",
                    "The table output does not provide tenant ID or region in all PAC CLI versions.",
                ],
            }

        no_environment_message = " ".join(table_output.casefold().split())
        if table_result.succeeded and any(marker in no_environment_message for marker in ("no environments found", "no environments available", "no records found")):
            return {
                "success": True,
                "count": 0,
                "active_profile": active,
                "environments": [],
                "discovery_format": "table_fallback",
                "notice": "The active Power Platform profile did not return any visible environments.",
                "scope": "tenant_environments_visible_to_pac_admin_list_for_the_active_profile",
                "limitations": ["Environment visibility depends on the signed-in user's permissions."],
            }

        error_text = (table_result.stderr or table_result.stdout or "").casefold()
        if any(marker in error_text for marker in ("403", "forbidden", "unauthorized", "insufficient privilege", "not authorized")):
            friendly_error = (
                "Your Power Platform account is signed in, but it cannot list tenant environments. "
                "Ask your administrator to confirm the required environment or tenant discovery permissions."
            )
            diagnostic_code = "environment_discovery_permission_denied"
        elif not table_result.succeeded:
            friendly_error = (
                "PAC CLI could not list Power Platform environments in either JSON or standard table mode. "
                "Check the active PAC CLI profile and run `pac admin list` in PowerShell to verify access."
            )
            diagnostic_code = "environment_list_command_failed"
        else:
            friendly_error = (
                "PAC CLI returned an environment list that SKYFALL could not recognize. "
                "Both JSON and standard table formats were attempted. Check the output of `pac admin list` and update PAC CLI if needed."
            )
            diagnostic_code = "environment_list_format_unrecognized"

        return {
            "success": False,
            "error": friendly_error,
            "diagnostic_code": diagnostic_code,
            "json_attempt": "unusable",
            "table_fallback": "unusable",
            "active_profile": active,
            "environments": [],
            "details": {
                "json_issue": json_error,
                "table_exit_code": table_result.returncode,
            },
            "required_access": "The active profile must be permitted to enumerate the environments visible to it.",
        }
