"""Contract tests for v1.1 Modules 3.2-3.5 Power Platform application catalog.

All Power Platform REST traffic is faked: no tenant, network or credentials.
Bearer tokens must never appear in returned data or errors.
"""

from __future__ import annotations

import unittest
from typing import Any

from skyfall_cloud.msal_identity import POWER_PLATFORM_SCOPE
from skyfall_cloud.powerplatform_catalog import (
    PowerPlatformCatalog,
    PowerPlatformCatalogError,
)

TOKEN = "CATALOG_SECRET_TOKEN"
ENV_ID = "11111111-2222-3333-4444-555555555555"
ENV_URL = "https://qa.crm.dynamics.com"


class FakeProfile:
    def __init__(self, profile_id: str, provider: str = "powerplatform") -> None:
        self.profile_id = profile_id
        self.provider = provider


class FakeRegistry:
    def __init__(self) -> None:
        self.profiles: dict[str, FakeProfile] = {}

    def get_profile(self, profile_id: str | None) -> FakeProfile | None:
        if profile_id is None:
            return next(iter(self.profiles.values()), None)
        return self.profiles.get(profile_id)


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
        self.status = 200

    def get(self, url, params=None, headers=None, timeout=None) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if self.status != 200:
            return FakeResponse(self.status, {})
        if "/powerautomate/environments/" in url and url.endswith("/flows"):
            return FakeResponse(200, {"value": [
                {"id": "flow-1", "displayName": "Sync QA", "state": "Started", "createdBy": "admin"},
                {"id": "flow-2", "displayName": "Archived", "state": "Stopped"},
            ]})
        if "/powerapps/environments/" in url and url.endswith("/apps"):
            return FakeResponse(200, {"value": [
                {"id": "app-1", "displayName": "Tracker", "appType": "Canvas", "state": "Ready"},
            ]})
        if "/api/data/" in url and url.endswith("/solutions"):
            return FakeResponse(200, {"value": [
                {"solutionid": "sol-1", "friendlyname": "Core", "uniquename": "core",
                 "version": "1.0.0.0", "ismanaged": False, "publisherName": "IT"},
            ]})
        if "/powerautomate/environments/" in url and url.endswith("/connections"):
            return FakeResponse(200, {"value": [
                {"id": "conn-1", "displayName": "SharePoint", "status": "Connected"},
                {"id": "conn-2", "displayName": "Broken SQL", "status": "Error"},
            ]})
        return FakeResponse(200, {"value": []})


class TestPowerPlatformCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = FakeAuthority()
        self.pp = FakeProfile("pp-1")
        self.azure = FakeProfile("az-1", "azure")
        self.authority.registry.profiles = {self.pp.profile_id: self.pp, self.azure.profile_id: self.azure}
        self.http = FakeHttp()
        self.catalog = PowerPlatformCatalog(self.authority, http_client=self.http)

    def test_list_flows_parses_records(self) -> None:
        result = self.catalog.list_flows(ENV_ID)
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["flows"][0]["name"], "Sync QA")
        self.assertEqual(result["flows"][0]["state"], "Started")
        self.assertNotIn(TOKEN, str(result))
        self.assertEqual(self.authority.requested_scopes[0], [POWER_PLATFORM_SCOPE])
        self.assertEqual(self.http.calls[0]["headers"]["Authorization"], f"Bearer {TOKEN}")

    def test_list_apps_parses_records(self) -> None:
        result = self.catalog.list_apps(ENV_ID)
        self.assertTrue(result["success"])
        self.assertEqual(result["apps"][0]["app_type"], "Canvas")
        self.assertNotIn(TOKEN, str(result))

    def test_list_solutions_uses_dataverse_url(self) -> None:
        result = self.catalog.list_solutions(ENV_ID, ENV_URL)
        self.assertTrue(result["success"])
        self.assertEqual(result["solutions"][0]["unique_name"], "core")
        self.assertFalse(result["solutions"][0]["managed"])
        self.assertIn("/api/data/v9.2/solutions", self.http.calls[0]["url"])
        self.assertNotIn(TOKEN, str(result))

    def test_list_connections_parses_records(self) -> None:
        result = self.catalog.list_connections(ENV_ID)
        self.assertTrue(result["success"])
        self.assertEqual(result["connections"][1]["status"], "Error")
        self.assertNotIn(TOKEN, str(result))

    def test_denied_access_is_token_safe(self) -> None:
        self.http.status = 403
        for result in (
            self.catalog.list_flows(ENV_ID),
            self.catalog.list_apps(ENV_ID),
            self.catalog.list_connections(ENV_ID),
        ):
            with self.subTest(result=result):
                self.assertFalse(result["success"])
                self.assertNotIn(TOKEN, str(result))
                self.assertIn("permissions", result["error"].lower())

    def test_azure_profile_cannot_drive_catalog(self) -> None:
        with self.assertRaises(ValueError):
            self.catalog.list_flows(ENV_ID, self.azure.profile_id)
        with self.assertRaises(ValueError):
            self.catalog.list_apps(ENV_ID, self.azure.profile_id)
        self.assertEqual(self.http.calls, [])

    def test_invalid_environment_id_rejected(self) -> None:
        with self.assertRaises(PowerPlatformCatalogError):
            self.catalog.list_flows("../../evil")

    def test_ssrf_environment_url_validation(self) -> None:
        for bad in (
            "http://qa.crm.dynamics.com",
            "https://evil.example.com",
            "https://qa.crm.dynamics.com.attacker.com",
            "https://user@qa.crm.dynamics.com",
            "https://qa.crm.dynamics.com:8443",
            "not-a-url",
        ):
            with self.subTest(url=bad):
                with self.assertRaises(PowerPlatformCatalogError):
                    PowerPlatformCatalog.validate_environment_url(bad)
        self.assertEqual(
            PowerPlatformCatalog.validate_environment_url(ENV_URL + "/"), ENV_URL
        )

    def test_intelligence_helpers(self) -> None:
        flows = self.catalog.list_flows(ENV_ID)["flows"]
        inactive = self.catalog.find_inactive_flows(flows)
        self.assertEqual([f["flow_id"] for f in inactive], ["flow-2"])
        connections = self.catalog.list_connections(ENV_ID)["connections"]
        broken = self.catalog.find_broken_connections(connections)
        self.assertEqual([c["connection_id"] for c in broken], ["conn-2"])
        self.assertTrue(self.catalog.compare_catalogs({"flows": 2}, {"flows": 2})["same"])
        self.assertFalse(self.catalog.compare_catalogs({"flows": 2}, {"flows": 3})["same"])


if __name__ == "__main__":
    unittest.main()
