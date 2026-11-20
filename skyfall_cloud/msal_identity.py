"""Unified MSAL identity authority for SKYFALL v1.1 (Module 4).

Provider-neutral facade for Microsoft Entra ID authentication across Azure and
Power Platform. It deliberately keeps the two providers' sessions INDEPENDENT:
authenticating to Azure never implies Power Platform access, and vice versa
(v1.1 spec Module 4, "Important" note).

Security invariants:
    * Profile metadata and health/diagnostic output NEVER contain tokens,
        secrets, client secrets or cache bytes.
    * Each profile gets an isolated, OS-protected encrypted token cache.
    * Token acquisition tries silent refresh first; interactive sign-in is
        explicit and opt-in via ``allow_interactive``.
    * All Microsoft calls go through the official MSAL library.

The MSAL application and token cache are dependency-injected so the module is
fully unit-testable with fakes (no live tenant, network or credentials needed).
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol


_GUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
# A scope must be ONE well-formed OAuth scope URL. MSAL joins scope arrays with
# spaces, so a whitespace-containing element could otherwise smuggle a second
# provider's scope into a token request (cross-provider grant bypass).
_SCOPE_VALUE = re.compile(r"^https://[A-Za-z0-9.-]+/[A-Za-z0-9._/-]+$")

AZURE_SCOPE = "https://management.azure.com/.default"
POWER_PLATFORM_SCOPE = "https://api.powerplatform.com/.default"
GRAPH_USER_SCOPE = "https://graph.microsoft.com/User.Read"

# Least-privilege defaults: a profile may only request scopes from its provider.
PROVIDER_SCOPE_PREFIXES: dict[str, tuple[str, ...]] = {
    "azure": ("https://management.azure.com/", "https://graph.microsoft.com/"),
    "powerplatform": ("https://api.powerplatform.com/", "https://graph.microsoft.com/"),
}


class IdentityProvider(str, Enum):
    AZURE = "azure"
    POWER_PLATFORM = "powerplatform"


class MsalApplication(Protocol):
    """Minimal surface of msal.PublicClientApplication used here."""

    def get_accounts(self, username: str | None = None) -> list[dict[str, Any]]: ...

    def acquire_token_silent(
        self, scopes: list[str], account: dict[str, Any] | None
    ) -> dict[str, Any] | None: ...

    def acquire_token_interactive(
        self, scopes: list[str], prompt: str, timeout: int
    ) -> dict[str, Any]: ...


AppFactory = Callable[[str, str, Any], MsalApplication]
CacheFactory = Callable[[Path], Any]


def _default_cache_factory(path: Path) -> Any:
    from msal_extensions import PersistedTokenCache
    from msal_extensions.persistence import build_encrypted_persistence

    return PersistedTokenCache(build_encrypted_persistence(str(path)))


def _default_app_factory(client_id: str, authority: str, token_cache: Any) -> MsalApplication:
    import msal

    return msal.PublicClientApplication(client_id, authority=authority, token_cache=token_cache)


_KNOWN_ERROR_CODES = {
    "invalid_client", "unauthorized_client", "interaction_required", "login_required",
    "consent_required", "invalid_request", "invalid_grant", "authentication_failed",
    "client_error", "service_error", "temporarily_unavailable",
}


def _safe_token_error(result: dict[str, Any] | None) -> str:
    """Return a user-facing identity error, never a raw/echoed MSAL response."""
    raw_code = str((result or {}).get("error") or "")
    code = raw_code if raw_code in _KNOWN_ERROR_CODES else "authentication_failed"
    if code in {"invalid_client", "unauthorized_client"}:
        return "Microsoft rejected the app registration. Check the client ID and enable public client flows."
    if code in {"interaction_required", "login_required", "consent_required"}:
        return "This profile needs Microsoft sign-in again. Reconnect it to continue."
    return f"Microsoft sign-in failed ({code}). Check app registration permissions and tenant consent."


@dataclass
class ProfileRecord:
    """Secret-free identity profile metadata."""

    profile_id: str
    name: str
    provider: str
    tenant_id: str
    username: str
    scopes: list[str]
    client_id: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IdentityRegistry:
    """Persistent, secret-free registry of MSAL identity profiles."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else (
            Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SKYFALL" / "identity"
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "profiles.json"

    _REQUIRED_FIELDS = (
        "profile_id", "name", "provider", "tenant_id", "username",
        "scopes", "client_id", "created_at",
    )

    def _read(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"schema_version": 1, "active": {"azure": None, "powerplatform": None}, "profiles": []}
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Identity registry could not be read: {exc}") from exc
        if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("profiles"), list):
            raise ValueError("Identity registry has an unsupported format.")

        # Validate shapes defensively: a partial/corrupt entry must not raise a
        # TypeError deep inside profile construction or health reporting.
        active_data = data.get("active")
        active_data = active_data if isinstance(active_data, dict) else {}
        active = {
            provider: value if isinstance(value, str) and _GUID.fullmatch(value) else None
            for provider in ("azure", "powerplatform")
            for value in (active_data.get(provider),)
        }
        profiles: list[dict[str, Any]] = []
        for item in data["profiles"]:
            if not isinstance(item, dict) or any(field not in item for field in self._REQUIRED_FIELDS):
                continue
            if not _GUID.fullmatch(str(item["profile_id"])):
                continue
            if item["provider"] not in ("azure", "powerplatform"):
                continue
            if not isinstance(item["scopes"], list) or not all(isinstance(s, str) for s in item["scopes"]):
                continue
            if not all(isinstance(item[field], str) for field in self._REQUIRED_FIELDS if field != "scopes"):
                continue
            profiles.append({field: item[field] for field in self._REQUIRED_FIELDS})
        return {"schema_version": 1, "active": active, "profiles": profiles}

    def _write(self, data: dict[str, Any]) -> None:
        # Unique temp file prevents concurrent writers from colliding on a
        # fixed .tmp path; os.replace keeps the registry atomic on Windows.
        temporary = self.registry_path.with_name(
            f".{self.registry_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, self.registry_path)

    @contextmanager
    def _exclusive(self):
        """Short-lived cross-process lock around read-modify-write mutations."""
        lock_path = self.registry_path.with_name(f".{self.registry_path.name}.lock")
        handle: int | None = None
        deadline = time.monotonic() + 5.0
        while handle is None:
            try:
                handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise ValueError("The identity registry is busy. Try again shortly.")
                time.sleep(0.01)
        try:
            yield
        finally:
            os.close(handle)
            try:
                lock_path.unlink()
            except OSError:
                pass

    def list_profiles(self, provider: str | None = None) -> list[ProfileRecord]:
        profiles = [ProfileRecord(**item) for item in self._read()["profiles"]]
        if provider is not None:
            profiles = [p for p in profiles if p.provider == provider]
        return profiles

    def get_profile(self, profile_id: str | None = None) -> ProfileRecord | None:
        if profile_id is None:
            active = self._read()["active"]
            for provider in ("azure", "powerplatform"):
                if active.get(provider):
                    found = self.get_profile(active[provider])
                    if found is not None:
                        return found
            return None
        for item in self._read()["profiles"]:
            if item.get("profile_id") == profile_id:
                return ProfileRecord(**item)
        return None

    def upsert(self, profile: ProfileRecord, *, activate: bool = True) -> None:
        with self._exclusive():
            data = self._read()
            profiles = data["profiles"]
            index = next((i for i, p in enumerate(profiles) if p["profile_id"] == profile.profile_id), None)
            record = profile.to_dict()
            if index is None:
                profiles.append(record)
            else:
                profiles[index] = {**profiles[index], **record}
            if activate:
                data["active"][profile.provider] = profile.profile_id
            self._write(data)

    def get_active_profile_id(self, provider: str) -> str | None:
        return self._read()["active"].get(provider)

    def select(self, profile_id: str) -> ProfileRecord:
        with self._exclusive():
            profile = self.get_profile(profile_id)
            if profile is None:
                raise KeyError("The selected identity profile no longer exists.")
            data = self._read()
            data["active"][profile.provider] = profile_id
            self._write(data)
            return profile

    def remove(self, profile_id: str) -> None:
        with self._exclusive():
            profile = self.get_profile(profile_id)
            data = self._read()
            data["profiles"] = [p for p in data["profiles"] if p["profile_id"] != profile_id]
            if profile and data["active"].get(profile.provider) == profile_id:
                remaining = [p for p in data["profiles"] if p["provider"] == profile.provider]
                data["active"][profile.provider] = remaining[0]["profile_id"] if remaining else None
            self._write(data)
            cache = self.cache_path(profile_id)
            if cache.exists():
                cache.unlink()

    def cache_path(self, profile_id: str) -> Path:
        if not _GUID.fullmatch(str(profile_id)):
            raise ValueError("Invalid identity profile identifier.")
        folder = self.root / "token_cache"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{profile_id}.bin"


@dataclass
class TokenDiagnostics:
    """Secret-free token status for health checks and UI display."""

    profile_id: str
    provider: str
    available: bool
    expires_on: int = 0
    scopes: list[str] | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UnifiedIdentityAuthority:
    """MSAL multi-identity authority with independent provider sessions."""

    def __init__(
        self,
        registry: IdentityRegistry | None = None,
        *,
        app_factory: AppFactory | None = None,
        cache_factory: CacheFactory | None = None,
    ) -> None:
        self.registry = registry or IdentityRegistry()
        self._app_factory = app_factory or _default_app_factory
        self._cache_factory = cache_factory or _default_cache_factory

    # -- validation --------------------------------------------------------

    @staticmethod
    def validate_tenant(tenant: str) -> str:
        value = (tenant or "").strip() or "organizations"
        if (
            not value
            or len(value) > 200
            or any(c in value for c in "\r\n\t /\\?#%")
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ValueError("Enter a tenant ID, tenant domain, or leave blank for work and school accounts.")
        return value

    @staticmethod
    def validate_name(name: str) -> str:
        value = (name or "").strip()
        if not value or len(value) > 80:
            raise ValueError("Enter a profile name between 1 and 80 characters.")
        return value

    @staticmethod
    def validate_client_id(client_id: str) -> str:
        value = (client_id or "").strip()
        if not _GUID.fullmatch(value):
            raise ValueError("Enter the Application (client) ID GUID from your Microsoft Entra app registration.")
        return value

    def validate_scopes(self, provider: str, scopes: list[str]) -> list[str]:
        """Reject scopes that do not belong to the requested provider."""
        allowed = PROVIDER_SCOPE_PREFIXES.get(provider)
        if allowed is None:
            raise ValueError(f"Unknown identity provider: {provider}")
        if not scopes:
            raise ValueError("At least one scope is required.")
        result: list[str] = []
        for scope in scopes:
            if not isinstance(scope, str) or not _SCOPE_VALUE.fullmatch(scope):
                raise ValueError(
                    "Scopes must be single, well-formed Microsoft OAuth scope URLs."
                )
            if not any(scope.startswith(prefix) for prefix in allowed):
                raise ValueError(f"Scope '{scope}' is not permitted for provider '{provider}'.")
            result.append(scope)
        return list(dict.fromkeys(result))

    # -- construction ------------------------------------------------------

    def _app(self, profile: ProfileRecord) -> MsalApplication:
        authority = f"https://login.microsoftonline.com/{profile.tenant_id}"
        cache = self._cache_factory(self.registry.cache_path(profile.profile_id))
        return self._app_factory(profile.client_id, authority, cache)

    def add_profile(
        self,
        *,
        provider: str,
        name: str,
        client_id: str,
        tenant: str = "organizations",
        scopes: list[str] | None = None,
    ) -> ProfileRecord:
        """Register a profile and perform the initial interactive MSAL sign-in."""
        if provider not in {p.value for p in IdentityProvider}:
            raise ValueError(f"Unknown identity provider: {provider}")
        clean_name = self.validate_name(name)
        clean_client = self.validate_client_id(client_id)
        clean_tenant = self.validate_tenant(tenant)
        default_scope = AZURE_SCOPE if provider == "azure" else POWER_PLATFORM_SCOPE
        clean_scopes = self.validate_scopes(provider, scopes or [default_scope])

        profile = ProfileRecord(
            profile_id=str(uuid.uuid4()),
            name=clean_name,
            provider=provider,
            tenant_id=clean_tenant,
            username="",
            scopes=clean_scopes,
            client_id=clean_client,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        try:
            result = self._app(profile).acquire_token_interactive(
                scopes=clean_scopes, prompt="select_account", timeout=300
            )
        except Exception:
            result = None
        if not result or not result.get("access_token"):
            raise RuntimeError(_safe_token_error(result))
        claims = result.get("id_token_claims") or {}
        if not isinstance(claims, dict):
            claims = {}
        profile.username = str(claims.get("preferred_username") or "Microsoft account")[:200]
        # Only a canonical tenant GUID from the signed claim may replace the
        # configured tenant; a malformed value must never reach the authority URL.
        raw_tid = str(claims.get("tid") or "").strip()
        if _GUID.fullmatch(raw_tid):
            profile.tenant_id = raw_tid
        self.registry.upsert(profile)
        return profile

    # -- account switching -------------------------------------------------

    def select_profile(self, profile_id: str) -> ProfileRecord:
        """Set the active profile for its provider (independent per provider)."""
        return self.registry.select(profile_id)

    # -- token acquisition -------------------------------------------------

    def acquire_token(
        self,
        profile_id: str,
        *,
        scopes: list[str] | None = None,
        allow_interactive: bool = False,
    ) -> str:
        """Return an access token to internal callers only (never via health)."""
        profile = self.registry.get_profile(profile_id)
        if profile is None:
            raise KeyError("The selected identity profile no longer exists.")
        requested = self.validate_scopes(profile.provider, scopes or profile.scopes)
        app: MsalApplication | None = None
        try:
            app = self._app(profile)
            accounts = app.get_accounts(username=profile.username or None)
            result = app.acquire_token_silent(requested, account=accounts[0]) if accounts else None
        except Exception:
            result = None
        if not result or not result.get("access_token"):
            if not allow_interactive:
                raise RuntimeError("Interactive sign-in is required but was not permitted for this request.")
            if app is not None:
                try:
                    result = app.acquire_token_interactive(
                        scopes=requested, prompt="select_account", timeout=300
                    )
                except Exception:
                    result = None
        if not result or not result.get("access_token"):
            raise RuntimeError(_safe_token_error(result))
        return str(result["access_token"])

    # -- health / diagnostics (strictly secret-free) -----------------------

    def health(self, profile_id: str | None = None) -> list[TokenDiagnostics]:
        try:
            profiles = (
                [self.registry.get_profile(profile_id)]
                if profile_id
                else self.registry.list_profiles()
            )
        except Exception:
            # A corrupt registry must degrade health, not crash the caller.
            return [TokenDiagnostics(
                profile_id=profile_id or "",
                provider="unknown",
                available=False,
                detail="Identity registry unavailable",
            )]
        diagnostics: list[TokenDiagnostics] = []
        for profile in profiles:
            if profile is None:
                continue
            try:
                app = self._app(profile)
                accounts = app.get_accounts(username=profile.username or None)
                result = app.acquire_token_silent(profile.scopes, account=accounts[0]) if accounts else None
                if result and result.get("access_token"):
                    diagnostics.append(TokenDiagnostics(
                        profile_id=profile.profile_id,
                        provider=profile.provider,
                        available=True,
                        expires_on=int(result.get("expires_on") or 0),
                        scopes=list(profile.scopes),
                    ))
                else:
                    diagnostics.append(TokenDiagnostics(
                        profile_id=profile.profile_id,
                        provider=profile.provider,
                        available=False,
                        scopes=list(profile.scopes),
                        detail="Sign-in required",
                    ))
            except Exception as exc:  # pragma: no cover - defensive
                diagnostics.append(TokenDiagnostics(
                    profile_id=profile.profile_id,
                    provider=profile.provider,
                    available=False,
                    detail=f"Health check failed ({type(exc).__name__})",
                ))
        return diagnostics

    def overall_health(self) -> dict[str, Any]:
        items = [d.to_dict() for d in self.health()]
        return {
            "profiles": items,
            "azure_authenticated": sum(1 for d in items if d["provider"] == "azure" and d["available"]),
            "powerplatform_authenticated": sum(1 for d in items if d["provider"] == "powerplatform" and d["available"]),
            "sessions_independent": True,
            "token_material_returned": False,
        }
