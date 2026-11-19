from __future__ import annotations

import unittest

from skyfall_cloud.cross_platform_service import CrossPlatformService
from skyfall_cloud.monitoring_service import MonitoringService
from skyfall_cloud.operations_service import OperationsService
from skyfall_cloud.reporting_service import ReportingService
from skyfall_cloud.audit_service import AuditService
from skyfall_cloud.identity_service import IdentityService


class CrossPlatformTests(unittest.TestCase):
    def test_drift_detection(self):
        cp = CrossPlatformService()
        r = cp.compare_configurations([{"name": "x", "v": 1}], [{"name": "x", "v": 2}])
        self.assertEqual(r["drift_count"], 1)


class MonitoringTests(unittest.TestCase):
    def test_inactive_detection(self):
        m = MonitoringService()
        res = m.detect_inactive([{"lastUsed": "2020-01-01T00:00:00+00:00"}], days=30)
        self.assertEqual(len(res), 1)

    def test_cost_anomaly(self):
        m = MonitoringService()
        res = m.detect_cost_anomaly([10, 10, 15], threshold=0.2)
        self.assertEqual(len(res), 1)


class OperationsTests(unittest.TestCase):
    def test_approval_denied(self):
        op = OperationsService()
        plan = op.plan_operation("delete", "x")
        self.assertFalse(op.execute(plan)["success"])


class ReportingTests(unittest.TestCase):
    def test_csv_json_md(self):
        r = ReportingService()
        rows = [{"a": 1, "b": "x"}]
        self.assertIn("a,b", r.to_csv(rows))
        self.assertIn('"a": 1', r.to_json(rows))
        self.assertTrue(r.to_markdown_table(rows).startswith("| a"))


class AuditTests(unittest.TestCase):
    def test_record_and_export(self):
        a = AuditService()
        a.record("read", "u", "t", {"k": 1})
        self.assertEqual(len(a.history()), 1)
        self.assertIn("read", a.export_json())


class IdentityTests(unittest.TestCase):
    def test_overall_health_empty(self):
        svc = IdentityService()
        h = svc.overall_health()
        self.assertEqual(h["azure_authenticated_count"], 0)
        self.assertFalse(h["credential_material_returned"])


if __name__ == "__main__":
    unittest.main()
import unittest
from app.desktop.sections import section_keys, section_by_key
from skyfall_cloud.azure_sdk_service import AzureSdkService

class SectionsTests(unittest.TestCase):
    def test_eleven_sections(self):
        self.assertEqual(len(section_keys()), 11)
        self.assertIsNotNone(section_by_key("azure"))

class SdkTests(unittest.TestCase):
    def test_sdk_available(self):
        s = AzureSdkService()
        r = s.sdk_available()
        self.assertIn("resource_graph", r)
