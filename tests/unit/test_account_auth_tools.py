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


class FakePowerPlatformDiscovery:
    def __init__(self):
        pass

    def create_profile_and_login(self, profile_name, environment):
        return {"success": True}


class AccountAuthToolTests(unittest.TestCase):
    def test_powerplatform_login_requires_global_profile_confirmation(self):
        jobs = FakeJobs()
        with patch.object(accounts, "AUTH_JOBS", jobs), patch.object(
            accounts, "PowerPlatformDiscovery", FakePowerPlatformDiscovery
        ):
            result = json.loads(accounts.start_powerplatform_login("Company QA"))
        self.assertTrue(result["requires_confirmation"])
        self.assertFalse(result.get("login_started", False))
        self.assertEqual(jobs.started, [])
        self.assertIn("globally active", result["warning"])

    def test_powerplatform_login_starts_after_explicit_confirmation(self):
        jobs = FakeJobs()
        with patch.object(accounts, "AUTH_JOBS", jobs), patch.object(
            accounts, "PowerPlatformDiscovery", FakePowerPlatformDiscovery
        ):
            result = json.loads(
                accounts.start_powerplatform_login(
                    "Company QA", "https://qa.crm.dynamics.com", True
                )
            )
        self.assertTrue(result["login_started"])
        self.assertEqual(result["job_id"], "auth-test-123")
        self.assertEqual(len(jobs.started), 1)

    def test_powerplatform_login_validates_profile_name_length(self):
        result = json.loads(accounts.start_powerplatform_login("X" * 31, confirm_global_profile_activation=True))
        self.assertIn("error", result)
        self.assertFalse(result.get("login_started", False))


if __name__ == "__main__":
    unittest.main()
