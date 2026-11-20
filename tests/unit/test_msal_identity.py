"""Unit tests for the v1.1 unified MSAL identity authority (Module 4).

All Microsoft interaction is faked: no live tenant, network, credentials or
GUI. Access tokens are asserted to never leak into health/diagnostic output.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from skyfall_cloud.msal_identity import (
    AZURE_SCOPE,
    POWER_PLATFORM_SCOPE,
    IdentityRegistry,
    UnifiedIdentityAuthority,
)


CLIENT_ID = "11111111-2222-3333-4444-555555555555"


class FakeCache:
    """Shared persisted-cache state: a fresh app over the same cache sees it."""

    def __init__(self) -> None:
        self.accounts: list[dict[str, Any]] = []
        self.silent_result: dict[str, Any] | None = None


class FakeApp:
    """In-memory stand-in for msal.PublicClientApplication."""

    def __init__(self, client_id: str, authority: str, token_cache: FakeCache) -> None:
        self.client_id = client_id
        self.authority = authority
        self.cache = token_cache
        self.interactive_result: dict[str, Any] = {
            "access_token": "FAKE_TOKEN_DO_NOT_LOG",
            "expires_on": 9999999999,
            "id_token_claims": {"preferred_username": "user@example.com", "tid": "tenant-1"},
        }
        self.interactive_calls = 0
        self.silent_scopes: list[list[str]] = []
        self.interactive_scopes: list[list[str]] = []
        self.silent_error: Exception | None = None
        self.interactive_error: Exception | None = None

    def get_accounts(self, username: str | None = None) -> list[dict[str, Any]]:
        return self.cache.accounts

    def acquire_token_silent(self, scopes: list[str], account: dict[str, Any] | None):
        self.silent_scopes.append(list(scopes))
        if self.silent_error is not None:
            raise self.silent_error
        return self.cache.silent_result

    def acquire_token_interactive(self, scopes: list[str], prompt: str, timeout: int):
        self.interactive_calls += 1
        self.interactive_scopes.append(list(scopes))
        if self.interactive_error is not None:
            raise self.interactive_error
        self.cache.accounts = [{"username": "user@example.com"}]
        return self.interactive_result


class TestUnifiedIdentityAuthority(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.registry = IdentityRegistry(Path(self.tmp.name))
        self.apps: list[FakeApp] = []
        self.caches: dict[str, FakeCache] = {}

        def cache_factory(path: Path) -> FakeCache:
            key = str(path)
            self.caches.setdefault(key, FakeCache())
            return self.caches[key]

        def app_factory(client_id: str, authority: str, token_cache: FakeCache) -> FakeApp:
            app = FakeApp(client_id, authority, token_cache)
            self.apps.append(app)
            return app

        self.authority = UnifiedIdentityAuthority(
            self.registry, app_factory=app_factory, cache_factory=cache_factory
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _add(self, provider: str, name: str) -> Any:
        return self.authority.add_profile(
            provider=provider, name=name, client_id=CLIENT_ID, tenant="organizations"
        )

    # -- validation --------------------------------------------------------

    def test_tenant_and_name_validation(self) -> None:
        self.assertEqual(self.authority.validate_tenant(""), "organizations")
        with self.assertRaises(ValueError):
            self.authority.validate_tenant("bad/tenant")
        with self.assertRaises(ValueError):
            self.authority.validate_name("")
        with self.assertRaises(ValueError):
            self.authority.validate_client_id("not-a-guid")
        with self.assertRaises(ValueError):
            self.authority.validate_tenant("organizations/../../evil")
        for hostile in ("org?#x", "org%2f", "org\nx", "org name"):
            with self.assertRaises(ValueError):
                self.authority.validate_tenant(hostile)

    def test_scope_provider_isolation(self) -> None:
        with self.assertRaises(ValueError):
            self.authority.validate_scopes("powerplatform", [AZURE_SCOPE])
        with self.assertRaises(ValueError):
            self.authority.validate_scopes("azure", [POWER_PLATFORM_SCOPE])
        self.assertEqual(
            self.authority.validate_scopes("azure", [AZURE_SCOPE]),
            [AZURE_SCOPE],
        )

    def test_whitespace_scope_bypass_is_rejected(self) -> None:
        # MSAL joins scope arrays with spaces; a single element containing a
        # second provider's scope must never reach an MSAL token request.
        bypass = f"{AZURE_SCOPE} {POWER_PLATFORM_SCOPE}"
        with self.assertRaises(ValueError):
            self.authority.validate_scopes("azure", [bypass])
        with self.assertRaises(ValueError):
            self.authority.validate_scopes("powerplatform", [bypass])
        with self.assertRaises(ValueError):
            self.authority.validate_scopes("azure", [AZURE_SCOPE + "\n" + POWER_PLATFORM_SCOPE])
        with self.assertRaises(ValueError):
            self.authority.add_profile(
                provider="azure", name="Bypass", client_id=CLIENT_ID, scopes=[bypass]
            )
        self.assertEqual(self.apps, [])

    # -- profile lifecycle -------------------------------------------------

    def test_add_profile_uses_interactive_signin_and_stores_no_secret(self) -> None:
        profile = self._add("azure", "My Azure")
        self.assertEqual(profile.provider, "azure")
        self.assertEqual(profile.username, "user@example.com")
        self.assertNotIn("access_token", str(profile.to_dict()))
        stored = self.registry.registry_path.read_text(encoding="utf-8")
        self.assertNotIn("FAKE_TOKEN", stored)

    def test_active_profile_tracked_per_provider(self) -> None:
        azure = self._add("azure", "Azure 1")
        pp = self._add("powerplatform", "PP 1")
        self.assertEqual(self.registry.get_active_profile_id("azure"), azure.profile_id)
        self.assertEqual(self.registry.get_active_profile_id("powerplatform"), pp.profile_id)
        self.authority.select_profile(azure.profile_id)
        self.assertEqual(self.registry.get_active_profile_id("azure"), azure.profile_id)
        self.assertEqual(self.registry.get_active_profile_id("powerplatform"), pp.profile_id)

    # -- token acquisition -------------------------------------------------

    def test_silent_token_refresh_preferred(self) -> None:
        profile = self._add("azure", "Azure 1")
        cache = self.caches[str(self.registry.cache_path(profile.profile_id))]
        cache.silent_result = {"access_token": "SILENT", "expires_on": 1}
        token = self.authority.acquire_token(profile.profile_id, scopes=[AZURE_SCOPE])
        self.assertEqual(token, "SILENT")
        # Only the add_profile interactive call happened; refresh stayed silent.
        self.assertEqual(sum(app.interactive_calls for app in self.apps), 1)

    def test_interactive_requires_explicit_permission(self) -> None:
        profile = self._add("azure", "Azure 1")
        with self.assertRaises(RuntimeError):
            self.authority.acquire_token(profile.profile_id)
        token = self.authority.acquire_token(profile.profile_id, allow_interactive=True)
        self.assertEqual(token, "FAKE_TOKEN_DO_NOT_LOG")

    # -- health is secret-free ---------------------------------------------

    def test_health_never_exposes_tokens(self) -> None:
        profile = self._add("azure", "Azure 1")
        cache = self.caches[str(self.registry.cache_path(profile.profile_id))]
        cache.silent_result = {
            "access_token": "SECRET_TOKEN_VALUE",
            "expires_on": 1234567890,
        }
        health = self.authority.overall_health()
        rendered = str(health)
        self.assertNotIn("SECRET_TOKEN_VALUE", rendered)
        self.assertNotIn("access_token", rendered)
        self.assertTrue(health["token_material_returned"] is False)
        self.assertTrue(health["sessions_independent"])
        self.assertEqual(health["azure_authenticated"], 1)
        self.assertEqual(health["powerplatform_authenticated"], 0)
        self.assertEqual(health["profiles"][0]["expires_on"], 1234567890)

    def test_sessions_independent_across_providers(self) -> None:
        azure = self._add("azure", "Azure 1")
        pp = self._add("powerplatform", "PP 1")
        self.assertNotEqual(azure.profile_id, pp.profile_id)
        self.assertNotEqual(
            self.registry.cache_path(azure.profile_id),
            self.registry.cache_path(pp.profile_id),
        )
        health = self.authority.overall_health()
        self.assertEqual(len(health["profiles"]), 2)
        self.assertEqual(
            {p["provider"] for p in health["profiles"]},
            {"azure", "powerplatform"},
        )
        # Each provider's token request used only that provider's scopes.
        azure_app = self.apps[0]
        pp_app = self.apps[1]
        self.assertEqual(azure_app.interactive_scopes, [[AZURE_SCOPE]])
        self.assertEqual(pp_app.interactive_scopes, [[POWER_PLATFORM_SCOPE]])
        for scope in azure_app.interactive_scopes[0]:
            self.assertNotIn("powerplatform", scope)
        for scope in pp_app.interactive_scopes[0]:
            self.assertNotIn("management.azure.com", scope)

    # -- hardened failure paths --------------------------------------------

    def test_forged_tid_cannot_influence_authority(self) -> None:
        app = FakeApp("", "", FakeCache())
        app.interactive_result = {
            "access_token": "FAKE_TOKEN_DO_NOT_LOG",
            "id_token_claims": {
                "preferred_username": "user@example.com",
                "tid": "evil/../../attacker?#",
            },
        }
        self.apps.append(app)
        captured: dict[str, str] = {}

        def factory(client_id: str, authority: str, cache: Any) -> FakeApp:
            captured["authority"] = authority
            return app

        self.authority._app_factory = factory
        profile = self._add("azure", "Forged claim")
        self.assertEqual(profile.tenant_id, "organizations")
        self.assertEqual(captured["authority"], "https://login.microsoftonline.com/organizations")
        self.assertNotIn("evil", captured["authority"])

    def test_valid_guid_tid_is_accepted(self) -> None:
        app = FakeApp("", "", FakeCache())
        tid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        app.interactive_result = {
            "access_token": "FAKE_TOKEN_DO_NOT_LOG",
            "id_token_claims": {"tid": tid},
        }
        self.apps.append(app)
        captured: dict[str, str] = {}

        def factory(client_id: str, authority: str, cache: Any) -> FakeApp:
            captured["authority"] = authority
            return app

        self.authority._app_factory = factory
        profile = self._add("azure", "Valid claim")
        self.assertEqual(profile.tenant_id, tid)
        # The authority is rebuilt from the persisted profile after sign-in,
        # so subsequent token calls use the canonical tenant claim.
        self.authority._app(profile)
        self.assertEqual(captured["authority"], f"https://login.microsoftonline.com/{tid}")

    def test_msal_exception_cannot_leak_token(self) -> None:
        profile = self._add("azure", "Azure 1")
        failing_app = FakeApp("", "", FakeCache())
        failing_app.silent_error = RuntimeError("MSAL failure while sending LEAK_ME")
        failing_app.interactive_error = RuntimeError("MSAL failure while sending LEAK_ME")
        self.authority._app_factory = lambda client_id, authority, cache: failing_app
        with self.assertRaises(RuntimeError) as raised:
            self.authority.acquire_token(profile.profile_id, allow_interactive=True)
        self.assertNotIn("LEAK_ME", str(raised.exception))
        health = self.authority.overall_health()
        self.assertNotIn("LEAK_ME", str(health))

    def test_app_factory_failure_yields_generic_auth_error(self) -> None:
        profile = self._add("azure", "Azure 1")
        self.authority._app_factory = lambda client_id, authority, cache: (_ for _ in ()).throw(
            RuntimeError("LEAK_ME from factory")
        )
        with self.assertRaises(RuntimeError) as raised:
            self.authority.acquire_token(profile.profile_id, allow_interactive=True)
        self.assertNotIn("LEAK_ME", str(raised.exception))
        self.assertNotIsInstance(raised.exception, UnboundLocalError)

    def test_echoed_error_code_is_whitelisted(self) -> None:
        profile = self._add("azure", "Azure 1")
        failing_app = FakeApp("", "", FakeCache())
        failing_app.silent_result = {"error": "attacker-controlled-echo-LEAK_ME"}
        self.authority._app_factory = lambda client_id, authority, cache: failing_app
        with self.assertRaises(RuntimeError) as raised:
            self.authority.acquire_token(profile.profile_id)
        self.assertNotIn("LEAK_ME", str(raised.exception))

    def test_corrupt_registry_degrades_health(self) -> None:
        self.registry.registry_path.write_text("{not json", encoding="utf-8")
        health = self.authority.overall_health()
        self.assertEqual(health["profiles"][0]["detail"], "Identity registry unavailable")
        self.assertFalse(health["profiles"][0]["available"])

    def test_malformed_profile_entry_is_ignored(self) -> None:
        self.registry.registry_path.write_text(
            '{"schema_version":1,"active":{"azure":null,"powerplatform":null},'
            '"profiles":[{"profile_id":"bad"}]}',
            encoding="utf-8",
        )
        self.assertEqual(self.registry.list_profiles(), [])
        self.assertEqual(self.authority.overall_health()["profiles"], [])

    def test_cache_path_rejects_traversal_identifier(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.cache_path("../../evil")


if __name__ == "__main__":
    unittest.main()
