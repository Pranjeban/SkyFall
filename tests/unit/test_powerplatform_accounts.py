from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skyfall_cloud.powerplatform_accounts import PowerPlatformAccountStore, PowerPlatformApi

CLIENT_ID = "11111111-2222-3333-4444-555555555555"
PROFILE_ID = "profile-1"

class Response:
    def __init__(self, status, payload):
        self.status_code, self.payload = status, payload
    def json(self):
        return self.payload

class HttpFake:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

class PowerPlatformAccountStoreTests(unittest.TestCase):
    def test_app_id_validation_and_profiles_persist_per_user_selection(self):
        with tempfile.TemporaryDirectory() as root:
            store = PowerPlatformAccountStore(root)
            with self.assertRaisesRegex(ValueError, "client ID GUID"):
                store.set_client_id("not-a-guid")
            store.set_client_id(CLIENT_ID)
            store.upsert_profile({"profile_id": PROFILE_ID, "name": "QA", "username": "qa@example.invalid", "tenant_id": "tenant", "selected_environment_id": ""})
            store.set_selected_environment(PROFILE_ID, "environment-guid")
            reloaded = PowerPlatformAccountStore(root)
            self.assertEqual(reloaded.get_client_id(), CLIENT_ID)
            self.assertEqual(reloaded.get_active_profile_id(), PROFILE_ID)
            self.assertEqual(reloaded.get_profile(PROFILE_ID)["selected_environment_id"], "environment-guid")

    def test_remove_profile_clears_selection_and_cache_file(self):
        with tempfile.TemporaryDirectory() as root:
            store = PowerPlatformAccountStore(root)
            store.upsert_profile({"profile_id": PROFILE_ID, "name": "QA", "username": "qa@example.invalid"})
            cache_file = store.token_cache_path(PROFILE_ID)
            cache_file.write_bytes(b"protected-cache")
            store.remove_profile(PROFILE_ID)
            self.assertIsNone(store.get_active_profile_id())
            self.assertEqual(store.list_profiles(), [])
            self.assertFalse(cache_file.exists())

class PowerPlatformApiTests(unittest.TestCase):
    def test_environment_list_normalizes_fields_and_follows_next_link(self):
        with tempfile.TemporaryDirectory() as root:
            store = PowerPlatformAccountStore(root)
            store.set_client_id(CLIENT_ID)
            store.upsert_profile({"profile_id": PROFILE_ID, "name": "QA", "username": "qa@example.invalid", "tenant_id": "tenant"})
            http = HttpFake([
                Response(200, {"value": [{"id": "{env-1}", "displayName": "QA Environment", "type": "Sandbox", "url": "https://qa.crm.dynamics.com", "dataverseId": "org-1"}], "@odata.nextLink": "https://api.powerplatform.com/page2"}),
                Response(200, {"value": [{"id": "env-2", "displayName": "Prod", "url": "https://prod.crm.dynamics.com"}]}),
            ])
            api = PowerPlatformApi(store, http_client=http)
            with patch.object(api, "_access_token", return_value="placeholder-token"):
                result = api.list_environments()
            self.assertTrue(result["success"])
            self.assertEqual(result["count"], 2)
            self.assertEqual(result["environments"][0]["environment_id"], "env-1")
            self.assertEqual(result["environments"][0]["environment_url"], "https://qa.crm.dynamics.com")
            self.assertEqual(http.calls[1][0], "https://api.powerplatform.com/page2")
            self.assertNotIn("placeholder-token", repr(result))

    def test_environment_permission_failure_returns_safe_diagnostic(self):
        with tempfile.TemporaryDirectory() as root:
            store = PowerPlatformAccountStore(root)
            store.set_client_id(CLIENT_ID)
            store.upsert_profile({"profile_id": PROFILE_ID, "name": "QA", "username": "qa@example.invalid"})
            api = PowerPlatformApi(store, http_client=HttpFake([Response(403, {"error": "secret server detail"})]))
            with patch.object(api, "_access_token", return_value="placeholder-token"):
                result = api.list_environments()
            self.assertFalse(result["success"])
            self.assertIn("delegated environment read permission", result["error"])
            self.assertNotIn("secret server detail", result["error"])

    def test_environment_pagination_rejects_external_host_before_following(self):
        with tempfile.TemporaryDirectory() as root:
            store = PowerPlatformAccountStore(root)
            store.set_client_id(CLIENT_ID)
            store.upsert_profile({"profile_id": PROFILE_ID, "name": "QA", "username": "qa@example.invalid"})
            http = HttpFake([Response(200, {"value": [], "@odata.nextLink": "https://attacker.invalid/collect"})])
            api = PowerPlatformApi(store, http_client=http)
            with patch.object(api, "_access_token", return_value="placeholder-token"):
                result = api.list_environments()
            self.assertFalse(result["success"])
            self.assertEqual(len(http.calls), 1)
            self.assertNotIn("placeholder-token", repr(result))

if __name__ == "__main__":
    unittest.main()
