"""Contract tests for the v1.1 unified-cloud MCP tool adapters.

Services are faked through the documented injection seam: no live Microsoft
tenant, network, credentials or GUI. Tokens must never reach tool output.
"""

from __future__ import annotations

import json
import unittest
from typing import Any

from skyfall_cloud.cloud_governance import CloudGovernanceService
from skyfall_cloud.cloud_monitoring import CloudMonitoringService
from skyfall_cloud.cloud_reporting import CloudReportingService
from skyfall_cloud.copilot_intents import CopilotIntentRouter
from skyfall_cloud.cross_platform_intelligence import CrossPlatformIntelligence
from skyfall_cloud.controlled_operations import ControlledOperationsService
from skyfall_mcp.tools import unified_cloud

TOKEN = "TOOL_SECRET_TOKEN"


class FakeIdentity:
    def overall_health(self) -> dict[str, Any]:
        return {"profiles": [], "sessions_independent": True, "token_material_returned": False}


class FakeAzureDiscovery:
    def tenant_subscription_overview(self, profile_id: str | None) -> dict[str, Any]:
        return {"profile_id": profile_id, "tenants": [], "subscriptions": [], "sessions_independent": True}


class FakeAzureInventory:
    def inventory(self, subscription_ids: list[str], categories: list[str] | None) -> dict[str, Any]:
        return {"success": True, "subscriptions": subscription_ids, "categories": categories, "count": 0}


class FakePpDiscovery:
    def list_environments(self, profile_id: str | None) -> dict[str, Any]:
        return {"success": True, "profile_id": profile_id, "environments": [], "count": 0}

    def get_environment(self, environment_id: str) -> dict[str, Any]:
        return {"environment_id": environment_id, "owners": ["Admin"]}


class FakeCatalog:
    def list_flows(self, environment_id: str, profile_id: str | None) -> dict[str, Any]:
        return {"success": True, "count": 2, "environment_id": environment_id}

    def list_apps(self, environment_id: str, profile_id: str | None) -> dict[str, Any]:
        return {"success": True, "count": 1}

    def list_connections(self, environment_id: str, profile_id: str | None) -> dict[str, Any]:
        return {"success": True, "count": 0}


class FakeOrchestration:
    def run(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "success": True,
            "steps": [{"id": "identity_health", "success": True, "error": None}],
            "token_material_returned": False,
        }


class ExplodingService:
    def __getattr__(self, name: str) -> Any:
        def explode(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError(f"request sent Authorization: Bearer {TOKEN}")
        return explode


class TestUnifiedCloudTools(unittest.TestCase):
    def setUp(self) -> None:
        governance = CloudGovernanceService()
        governance.record("tool_call", provider="azure", outcome="success")
        unified_cloud.configure_unified_cloud_services(
            identity=FakeIdentity(),
            azure_discovery=FakeAzureDiscovery(),
            azure_inventory=FakeAzureInventory(),
            powerplatform_discovery=FakePpDiscovery(),
            powerplatform_catalog=FakeCatalog(),
            orchestration=FakeOrchestration(),
            cross_platform=CrossPlatformIntelligence(),
            monitoring=CloudMonitoringService(),
            reporting=CloudReportingService(),
            governance=governance,
            operations=ControlledOperationsService(),
            copilot=CopilotIntentRouter(),
        )

    def tearDown(self) -> None:
        unified_cloud.configure_unified_cloud_services()

    @staticmethod
    def _parse(raw: str) -> dict[str, Any]:
        data = json.loads(raw)
        assert isinstance(data, dict)
        return data

    def test_identity_health_tool(self) -> None:
        result = self._parse(unified_cloud.get_unified_identity_health())
        self.assertTrue(result["sessions_independent"])
        self.assertFalse(result["token_material_returned"])

    def test_azure_discovery_tool(self) -> None:
        result = self._parse(unified_cloud.discover_azure_footprint("az-1"))
        self.assertEqual(result["profile_id"], "az-1")
        self.assertTrue(result["sessions_independent"])

    def test_azure_inventory_tool_parses_categories(self) -> None:
        result = self._parse(unified_cloud.inventory_azure_resources(
            ["s1", "s2"], "virtual_machines, function_apps"
        ))
        self.assertEqual(result["subscriptions"], ["s1", "s2"])
        self.assertEqual(result["categories"], ["virtual_machines", "function_apps"])
        all_categories = self._parse(unified_cloud.inventory_azure_resources(["s1"]))
        self.assertIsNone(all_categories["categories"])

    def test_powerplatform_tools(self) -> None:
        listed = self._parse(unified_cloud.discover_powerplatform_environments("pp-1"))
        self.assertEqual(listed["profile_id"], "pp-1")
        described = self._parse(unified_cloud.describe_powerplatform_environment("env-1"))
        self.assertEqual(described["environment_id"], "env-1")

    def test_exceptions_never_leak_tokens(self) -> None:
        unified_cloud.configure_unified_cloud_services(identity=ExplodingService())
        raw = unified_cloud.get_unified_identity_health()
        self.assertNotIn(TOKEN, raw)
        self.assertFalse(self._parse(raw)["success"])

    def test_catalog_tool(self) -> None:
        result = self._parse(unified_cloud.inspect_powerplatform_catalog("env-1"))
        self.assertTrue(result["success"])
        self.assertEqual(result["flows"]["count"], 2)
        self.assertEqual(result["apps"]["count"], 1)
        self.assertNotIn(TOKEN, str(result))

    def test_orchestration_tool(self) -> None:
        result = self._parse(unified_cloud.run_cloud_orchestration(
            azure_profile_id="az-1", subscription_ids="s1,s2"
        ))
        self.assertTrue(result["success"])
        self.assertEqual(result["steps"][0]["id"], "identity_health")
        self.assertNotIn(TOKEN, str(result))

    def test_json_backed_analysis_tools(self) -> None:
        azure = '[{"name":"vm","state":"Ready"}]'
        pp = '[{"environment_id":"e1","displayName":"QA"}]'
        correlation = self._parse(unified_cloud.correlate_cross_platform(azure, pp))
        self.assertEqual(correlation["inventory"]["count"], 2)
        self.assertEqual(correlation["gaps"]["count"], 2)
        health = self._parse(unified_cloud.cloud_health_report(azure, pp))
        self.assertTrue(health["success"])
        report = self._parse(unified_cloud.build_executive_report('{"subscriptions":[]}', pp))
        self.assertEqual(report["counts"]["powerplatform_environments"], 1)
        self.assertNotIn(TOKEN, str(report))

    def test_governance_copilot_and_operation_tools(self) -> None:
        governance = self._parse(unified_cloud.governance_summary())
        self.assertEqual(governance["summary"]["total"], 1)
        intent = self._parse(unified_cloud.route_copilot_intent("list power platform environments"))
        self.assertEqual(intent["operation"], "discover_powerplatform_environments")
        self.assertFalse(intent["executable"])
        plan = self._parse(unified_cloud.build_operation_plan(
            "azure.delete_resource", "azure", "/subscriptions/s1"
        ))
        self.assertEqual(plan["plan"]["risk"], "destructive")
        self.assertFalse(plan["plan"]["execution_permitted"])
        self.assertNotIn(TOKEN, str(plan))

    def test_new_adapters_never_leak_tokens(self) -> None:
        unified_cloud.configure_unified_cloud_services(operations=ExplodingService())
        raw = unified_cloud.build_operation_plan("azure.list_resources", "azure", "x")
        self.assertNotIn(TOKEN, raw)
        self.assertFalse(self._parse(raw)["success"])

    def test_mcp_server_exposes_all_v11_tools(self) -> None:
        from pathlib import Path

        server = (Path(__file__).resolve().parents[2] / "skyfall_mcp" / "server.py").read_text(
            encoding="utf-8"
        )
        for name in (
            "get_unified_identity_health", "discover_azure_footprint",
            "inventory_azure_resources", "discover_powerplatform_environments",
            "describe_powerplatform_environment", "inspect_powerplatform_catalog",
            "run_cloud_orchestration", "correlate_cross_platform",
            "cloud_health_report", "build_executive_report", "governance_summary",
            "route_copilot_intent", "build_operation_plan",
        ):
            with self.subTest(tool=name):
                self.assertIn(f"def {name}(", server)


if __name__ == "__main__":
    unittest.main()
