"""Contract tests for v1.1 Module 6 orchestration (no cloud/network)."""

from __future__ import annotations

import unittest
from typing import Any

from skyfall_cloud.cloud_orchestration import CloudOrchestrationService

TOKEN = "ORCH_SECRET_TOKEN"
ENV_ID = "11111111-2222-3333-4444-555555555555"


class FakeIdentity:
    def overall_health(self) -> dict[str, Any]:
        return {"profiles": [], "healthy": True, "token_material_returned": False}


class FakeAzureDiscovery:
    def __init__(self) -> None:
        self.profile: Any = "unset"

    def tenant_subscription_overview(self, profile_id: str | None) -> dict[str, Any]:
        self.profile = profile_id
        return {"success": True, "tenants": [1, 2], "subscriptions": [1, 2, 3]}


class FakeAzureInventory:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def inventory(self, subscription_ids: list[str], categories: list[str] | None = None) -> dict[str, Any]:
        self.calls.append({"subscriptions": subscription_ids, "categories": categories})
        return {"success": True, "count": 5}


class FakePpDiscovery:
    def __init__(self) -> None:
        self.profile: Any = "unset"
        self.http = object()

    def list_environments(self, profile_id: str | None) -> dict[str, Any]:
        self.profile = profile_id
        return {
            "success": True,
            "environments": [{"environment_id": ENV_ID, "name": "QA"}],
            "count": 1,
        }


class FakePpCatalog:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def list_flows(self, environment_id: str, profile_id: str | None = None) -> dict[str, Any]:
        self.calls.append(("flows", environment_id, profile_id))
        return {"success": True, "count": 2}

    def list_apps(self, environment_id: str, profile_id: str | None = None) -> dict[str, Any]:
        self.calls.append(("apps", environment_id, profile_id))
        return {"success": True, "count": 3}

    def list_connections(self, environment_id: str, profile_id: str | None = None) -> dict[str, Any]:
        self.calls.append(("connections", environment_id, profile_id))
        return {"success": True, "count": 1}


class TestCloudOrchestration(unittest.TestCase):
    def setUp(self) -> None:
        self.azure = FakeAzureDiscovery()
        self.inventory = FakeAzureInventory()
        self.pp = FakePpDiscovery()
        self.catalog = FakePpCatalog()
        self.service = CloudOrchestrationService(
            identity=FakeIdentity(),
            azure_discovery=self.azure,
            azure_inventory=self.inventory,
            pp_discovery=self.pp,
            pp_catalog=self.catalog,
            now=lambda: "2026-11-20T00:00:00+00:00",
        )

    def test_task_graph_is_read_only(self) -> None:
        graph = self.service.task_graph()
        self.assertEqual(len(graph), 5)
        self.assertTrue(all(step["read_only"] for step in graph))

    def test_full_run_correlates_counts(self) -> None:
        result = self.service.run(
            azure_profile_id="az-1", pp_profile_id="pp-1", subscription_ids=["s1"]
        )
        self.assertTrue(result["success"])
        self.assertTrue(all(step["success"] for step in result["steps"]))
        self.assertEqual(result["summary"]["total"], 5)
        self.assertEqual(result["correlated"]["azure"]["tenants"], 2)
        self.assertEqual(result["correlated"]["azure"]["resources"], 5)
        self.assertEqual(result["correlated"]["power_platform"]["environments"], 1)
        self.assertEqual(result["correlated"]["power_platform"]["flows"], 2)
        self.assertFalse(result["token_material_returned"])
        self.assertEqual(result["generated_at"], "2026-11-20T00:00:00+00:00")

    def test_profiles_never_cross_providers(self) -> None:
        self.service.run(azure_profile_id="az-1", pp_profile_id="pp-1", subscription_ids=["s1"])
        self.assertEqual(self.azure.profile, "az-1")
        self.assertEqual(self.pp.profile, "pp-1")
        self.assertEqual(self.inventory.calls[0]["subscriptions"], ["s1"])
        self.assertTrue(all(call[2] == "pp-1" for call in self.catalog.calls))

    def test_step_failure_is_isolated_and_token_safe(self) -> None:
        def explode(_profile: str | None) -> dict[str, Any]:
            raise RuntimeError(f"Authorization: Bearer {TOKEN} rejected")

        self.azure.tenant_subscription_overview = explode  # type: ignore[assignment]
        result = self.service.run(pp_profile_id="pp-1", subscription_ids=["s1"])
        footprint = next(s for s in result["steps"] if s["id"] == "azure_footprint")
        self.assertFalse(footprint["success"])
        self.assertNotIn(TOKEN, str(result))
        catalog = next(s for s in result["steps"] if s["id"] == "pp_catalog")
        self.assertTrue(catalog["success"])

    def test_returned_failure_error_is_redacted(self) -> None:
        self.pp.list_environments = lambda profile: {  # type: ignore[assignment]
            "success": False,
            "error": f"Microsoft said Bearer {TOKEN} is invalid",
        }
        result = self.service.run(subscription_ids=["s1"])
        env_step = next(s for s in result["steps"] if s["id"] == "pp_environments")
        self.assertFalse(env_step["success"])
        self.assertNotIn(TOKEN, str(result))
        self.assertIn("[REDACTED]", env_step["error"])

    def test_steps_skipped_without_inputs(self) -> None:
        self.pp.list_environments = lambda profile: {  # type: ignore[assignment]
            "success": True, "environments": [], "count": 0
        }
        result = self.service.run()
        inventory = next(s for s in result["steps"] if s["id"] == "azure_inventory")
        catalog = next(s for s in result["steps"] if s["id"] == "pp_catalog")
        self.assertTrue(inventory["success"])
        self.assertTrue(catalog["success"])
        self.assertTrue(inventory["skipped"])
        self.assertTrue(catalog["skipped"])

    def test_explicit_environment_used(self) -> None:
        other = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        self.service.run(environment_id=other)
        self.assertTrue(all(call[1] == other for call in self.catalog.calls))


if __name__ == "__main__":
    unittest.main()
