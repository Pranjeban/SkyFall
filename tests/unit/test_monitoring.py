from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from skyfall_cloud.monitoring import (
    AzureResourceHealthChecker,
    FunctionAppAvailabilityChecker,
    InactiveResourceDetector,
    PowerAutomateFailureDetector,
)


class MockClient:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def list_resources(self):
        self.calls.append("list_resources")
        return self.items

    def list_function_apps(self):
        self.calls.append("list_function_apps")
        return {"function_apps": self.items}

    def list_flows(self, *args, **kwargs):
        self.calls.append(("list_flows", args, kwargs))
        return self.items


class MonitoringTests(unittest.TestCase):
    def test_azure_health_checker_uses_mocked_client(self):
        client = MockClient([{"name": "vm-1", "status": "Available"}, {"name": "vm-2", "state": "Failed"}])
        checker = AzureResourceHealthChecker(client=client)
        result = checker.check()
        self.assertEqual(result["checked_count"], 2)
        self.assertEqual(result["unhealthy_count"], 1)
        self.assertEqual(client.calls, ["list_resources"])
        self.assertTrue(all(r["cloud_resources_modified"] is False for r in [result]))

    def test_function_app_availability(self):
        checker = FunctionAppAvailabilityChecker()
        result = checker.check([{"name": "app-a", "state": "Running"}, {"name": "app-b", "state": "Stopped"}])
        self.assertEqual(result["checked_count"], 2)
        self.assertEqual(result["unavailable_count"], 1)

    def test_power_automate_failure_detection_metadata_only(self):
        detector = PowerAutomateFailureDetector()
        flows = [
            {"flow_name": "good", "status": "Enabled"},
            {"flow_name": "bad", "status": "Failed", "definition": {"secret": "x"}},
        ]
        result = detector.detect(flows)
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["failures"][0]["name"], "bad")
        self.assertFalse(result["flow_definitions_read"])
        self.assertFalse(result["secrets_returned"])

    def test_inactive_detector_flags_old_items(self):
        now = datetime(2026, 11, 19, tzinfo=timezone.utc)
        detector = InactiveResourceDetector(inactive_days=30, now=now)
        old = now - timedelta(days=60)
        result = detector.detect(
            resources=[{"name": "vm-old", "state": "Stopped", "modified_on": old.isoformat()}],
            inactive_days=30,
        )
        self.assertEqual(result["inactive_count"], 1)
        self.assertIn("state is stopped", result["inactive"][0]["reasons"])

    def test_mocked_client_flow_detection(self):
        client = MockClient([{"flow_name": "f1", "status": "Failed"}])
        detector = PowerAutomateFailureDetector(client=client)
        result = detector.detect()
        self.assertEqual(result["failure_count"], 1)
        self.assertIn("list_flows", [c[0] if isinstance(c, tuple) else c for c in client.calls])

    def test_no_cloud_writes_flag(self):
        detector = InactiveResourceDetector()
        result = detector.detect(resources=[])
        self.assertFalse(result["cloud_resources_modified"])


if __name__ == "__main__":
    unittest.main()
