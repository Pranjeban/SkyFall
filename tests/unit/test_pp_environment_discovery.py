"""Unit tests for v1.1 Module 3.1 Power Platform environment intelligence.

All Power Platform REST traffic is faked: no tenant, network or credentials.
"""

from __future__ import annotations

import unittest
from typing import Any

from skyfall_cloud.powerplatform_discovery import PP_API_BASE, PowerPlatformDiscovery
from skyfall_cloud.msal_identity import POWER_PLATFORM_SCOPE

TOKEN = "PP_SECRET_TOKEN"
ENV_ID = "11111111-2222-3333-4444-555555555555"
OTHER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class FakeProfile:
    def __init__(self, profile_id: str, provider: str = "powerplatform") -> None:
        self.profile_id = profile_id
        self.provider = provider


class FakeRegistry:
    def __init__(self) -> None:
        self.profiles: dict[str, FakeProfile] = {}
        self.active: dict[str, str] = {}

    def get_profile(self, profile_id: str | None) -> FakeProfile | None:
        if profile_id is None:
            return next(iter(self.profiles.values()), None)
        return self.profiles.get(profile_id)

    def get_active_profile_id(self, provider: str) -> str | None:
        return self.active.get(provider)


class FakeAuthority:
    def __init__(self) -> None:
        self.registry = FakeRegistry()
        self.requested_scopes: list[list[str]] = []

    def acquire_token(self, profile_id: str, scopes: list[str] | None = None) -> str:
        self.requested_scopes.append(list(scopes or []))
        return TOKEN


class FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class FakeHttp:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.list_response = FakeResponse(200, {"value": [
            {
                "id": ENV_ID, "displayName": "QA", "environmentSku": "Production",
                "url": "https://qa.crm.dynamics.com", "azureRegion": "GB",
                "state": "Ready", "tenantId": "tenant-1", "dataverseId": "org-1",
                "isDefault": False, "createdTime": "2026-01-01",
            },
            {
                "id": OTHER_ID, "displayName": "Prod", "environmentSku": "Production",
                "url": "https://prod.crm.dynamics.com", "azureRegion": "US",
                "state": "Ready", "tenantId": "tenant-1", "dataverseId": "org-2",
            },
        ]})
        self.detail_response = FakeResponse(200, {
            "id": ENV_ID, "displayName": "QA", "environmentSku": "Production",
            "azureRegion": "GB", "state": "Ready", "tenantId": "tenant-1",
            "isDefault": False, "isDisabled": False, "vetoProtectionEnabled": True,
            "capacity": {"storage": "10GB"},
            "owners": [{"displayName": "Admin"}, {"id": "owner-2"}],
        })

    def get(self, url, params=None, headers=None, timeout=None) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return self.detail_response if url.endswith(ENV_ID) else self.list_response


class TestPowerPlatformDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = FakeAuthority()
        self.pp = FakeProfile("pp-1")
        self.azure = FakeProfile("az-1", "azure")
        self.authority.registry.profiles = {self.pp.profile_id: self.pp, self.azure.profile_id: self.azure}
        self.authority.registry.active = {
            "azure": self.azure.profile_id,
            "powerplatform": self.pp.profile_id,
        }
        self.http = FakeHttp()
        self.service = PowerPlatformDiscovery(self.authority, http_client=self.http)

    def test_list_environments_parses_records(self) -> None:
        result = self.service.list_environments()
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["environments"][0]["name"], "QA")
        self.assertEqual(result["environments"][0]["environment_id"], ENV_ID)
        self.assertNotIn(TOKEN, str(result))
        self.assertEqual(self.http.calls[0]["headers"]["Authorization"], f"Bearer {TOKEN}")
        self.assertEqual(self.authority.requested_scopes[0], [POWER_PLATFORM_SCOPE])

    def test_denied_access_is_token_safe(self) -> None:
        self.http.list_response = FakeResponse(403, {})
        result = self.service.list_environments()
        self.assertFalse(result["success"])
        self.assertNotIn(TOKEN, str(result))
        self.assertIn("permissions", result["error"].lower())

    def test_azure_profile_cannot_drive_pp_discovery(self) -> None:
        with self.assertRaises(ValueError):
            self.service.list_environments(self.azure.profile_id)
        self.assertEqual(self.http.calls, [])

    def test_default_profile_uses_provider_active_slot(self) -> None:
        # Azure is inserted first so the old cross-provider first-match logic
        # would resolve the wrong profile for a Power Platform call.
        self.authority.registry.profiles = {self.azure.profile_id: self.azure, self.pp.profile_id: self.pp}
        self.assertEqual(
            self.service._require_pp_profile(None).profile_id,
            self.pp.profile_id,
        )
        self.assertTrue(self.service.list_environments()["success"])

    def test_get_environment_details_and_sanitization(self) -> None:
        record = self.service.get_environment(ENV_ID)
        self.assertEqual(record["owners"], ["Admin", "owner-2"])
        self.assertTrue(record["security_flags"]["vetoProtectionEnabled"])
        self.assertEqual(record["capacity"]["storage"], "10GB")
        self.assertNotIn(TOKEN, str(record))

    def test_invalid_environment_id_rejected(self) -> None:
        with self.assertRaises(Exception):
            self.service.get_environment("../../evil")
        with self.assertRaises(Exception):
            self.service.select_environment("not-a-guid")

    def test_environment_switching_is_per_profile(self) -> None:
        self.assertEqual(self.service.active_environment(), None)
        self.service.select_environment(ENV_ID)
        self.assertEqual(self.service.active_environment(), ENV_ID)
        self.assertEqual(self.service.active_environment(self.pp.profile_id), ENV_ID)

    def test_compare_environments(self) -> None:
        left = {"environment_id": ENV_ID, "name": "QA", "type": "Production", "region": "GB", "state": "Ready", "tenant_id": "t", "organization_id": "o"}
        right = {**left, "environment_id": OTHER_ID, "region": "US"}
        result = self.service.compare_environments(left, right)
        self.assertFalse(result["same"])
        self.assertEqual([d["field"] for d in result["differences"]], ["region"])
        self.assertTrue(self.service.compare_environments(left, left)["same"])


if __name__ == "__main__":
    unittest.main()
