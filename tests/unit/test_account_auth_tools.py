from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from skyfall_mcp.tools import accounts


class FakeJobs:
    def __init__(self):
        self.started = []

    def start(self, label, operation):
        self.started.append((label, operation))
        return {"job_id": "auth-test-123", "status": "running", "label": label}


class FakePowerPlatformStore:
    def __init__(self):
        self.client_id = "11111111-2222-3333-4444-555555555555"

    def get_client_id(self):
        return self.client_id


class AccountAuthToolTests(unittest.TestCase):
    def test_azure_login_requests_missing_profile_and_tenant(self):
        result = json.loads(accounts.start_azure_login())
        self.assertEqual(result["requires_input"], ["profile_name", "tenant_id"])
        self.assertFalse(result["login_started"])

    def test_azure_login_requires_tenant_when_profile_name_is_provided(self):
        result = json.loads(accounts.start_azure_login(profile_name="Engineering"))
        self.assertEqual(result["requires_input"], ["tenant_id"])
        self.assertFalse(result["login_started"])

    def test_azure_login_is_blocked_in_test_mode(self):
        with patch.dict("os.environ", {"SKYFALL_TEST_MODE": "1"}):
            result = json.loads(accounts.start_azure_login("Engineering", "contoso.com"))
        self.assertEqual(result["status"], "blocked_test_mode")
        self.assertFalse(result["login_started"])

    def test_powerplatform_login_does_not_require_a_client_app_id(self):
        jobs = FakeJobs()
        with patch.object(accounts, "AUTH_JOBS", jobs):
            result = json.loads(accounts.start_powerplatform_login("Company QA"))
        self.assertTrue(result["login_started"])
        self.assertEqual(result["profile_name"], "Company QA")
        self.assertEqual(jobs.started[0][0], "Power Platform sign-in: Company QA")

    def test_powerplatform_login_is_blocked_in_test_mode(self):
        jobs = FakeJobs()
        with patch.object(accounts, "AUTH_JOBS", jobs), patch.dict("os.environ", {"SKYFALL_TEST_MODE": "1"}):
            result = json.loads(accounts.start_powerplatform_login("Company QA"))
        self.assertEqual(result["status"], "blocked_test_mode")
        self.assertFalse(result["login_started"])
        self.assertEqual(jobs.started, [])

    def test_powerplatform_login_accepts_optional_tenant_and_starts(self):
        jobs = FakeJobs()
        with patch.object(accounts, "AUTH_JOBS", jobs), patch.object(accounts, "PowerPlatformAccountStore", FakePowerPlatformStore):
            result = json.loads(accounts.start_powerplatform_login("Company QA", "contoso.com"))
        self.assertTrue(result["login_started"])
        self.assertEqual(result["job_id"], "auth-test-123")
        self.assertEqual(len(jobs.started), 1)

    def test_powerplatform_login_requires_profile_name(self):
        result = json.loads(accounts.start_powerplatform_login(""))
        self.assertEqual(result["requires_input"], ["profile_name"])
        self.assertFalse(result.get("login_started", False))


if __name__ == "__main__":
    unittest.main()
