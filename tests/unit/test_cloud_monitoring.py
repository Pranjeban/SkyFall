"""Contract tests for v1.1 Module 7 monitoring (no cloud/network)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from skyfall_cloud.cloud_monitoring import CloudMonitoringService, parse_timestamp

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)


class TestCloudMonitoring(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CloudMonitoringService()

    def test_parse_timestamp_variants(self) -> None:
        self.assertIsNotNone(parse_timestamp("2026-01-01T00:00:00Z"))
        self.assertIsNotNone(parse_timestamp("2026-01-01T00:00:00"))
        self.assertIsNotNone(parse_timestamp(NOW))
        for bad in (None, "", "not-a-date", 7, {}):
            with self.subTest(bad=bad):
                self.assertIsNone(parse_timestamp(bad))

    def test_detect_inactive_threshold(self) -> None:
        items = [
            {"name": "old", "lastUsed": "2026-09-01T00:00:00Z"},
            {"name": "new", "lastUsed": "2026-11-19T00:00:00Z"},
            {"name": "broken", "lastUsed": "garbage"},
            {"name": "missing"},
        ]
        result = self.service.detect_inactive(items, days=30, now=NOW)
        self.assertEqual([row["name"] for row in result], ["old"])

    def test_detect_stale_custom_field(self) -> None:
        items = [{"id": "a", "seenAt": "2026-01-01T00:00:00Z"}]
        self.assertEqual(len(self.service.detect_stale(items, "seenAt", 7, now=NOW)), 1)
        self.assertEqual(self.service.detect_stale(items, "absent", 7, now=NOW), [])

    def test_detect_state_anomalies(self) -> None:
        items = [
            {"name": "a", "state": "Started"},
            {"name": "b", "state": "Error"},
            {"name": "c", "state": "DISCONNECTED"},
        ]
        result = self.service.detect_state_anomalies(items)
        self.assertEqual([row["name"] for row in result], ["b", "c"])

    def test_detect_duplicates_deterministic(self) -> None:
        items = [
            {"environment_id": "e1"}, {"environment_id": "e2"},
            {"environment_id": "e1"}, {"environment_id": "e1"},
        ]
        self.assertEqual(
            self.service.detect_duplicates(items, "environment_id"),
            [{"key": "e1", "count": 3}],
        )

    def test_health_report_severity(self) -> None:
        healthy = self.service.health_report(
            azure_resources=[{"name": "vm", "lastUsed": "2026-11-19T00:00:00Z"}],
            pp_flows=[{"name": "flow", "state": "Started"}],
            now=NOW,
        )
        self.assertEqual(healthy["severity"], "healthy")
        critical = self.service.health_report(
            pp_flows=[{"state": "Error"}] * 5, now=NOW
        )
        self.assertEqual(critical["severity"], "critical")
        self.assertFalse(critical["token_material_returned"])

    def test_malformed_inputs_never_raise(self) -> None:
        for value in (None, 0, "x", {}, [None, "bad"]):
            with self.subTest(value=value):
                self.assertEqual(self.service.detect_inactive(value, now=NOW), [])
                self.assertEqual(self.service.detect_duplicates(value, "id"), [])
                self.assertEqual(self.service.health_report(value)["success"], True)


if __name__ == "__main__":
    unittest.main()
