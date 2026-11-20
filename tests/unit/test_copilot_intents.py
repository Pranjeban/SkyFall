"""Contract tests for v1.1 Module 1 Copilot intent routing (no execution)."""

from __future__ import annotations

import unittest

from skyfall_cloud.copilot_intents import CopilotIntentRouter

ENV_ID = "11111111-2222-3333-4444-555555555555"
TOKEN = "eyJCOPILOTSECRET1234567890"


class TestCopilotIntentRouter(unittest.TestCase):
    def setUp(self) -> None:
        self.router = CopilotIntentRouter()

    def test_azure_footprint_and_inventory(self) -> None:
        footprint = self.router.route("show me my azure tenants and subscriptions")
        self.assertEqual(footprint["operation"], "discover_azure_footprint")
        self.assertEqual(footprint["provider"], "azure")
        inventory = self.router.route("inventory the virtual machines and function apps")
        self.assertEqual(inventory["operation"], "inventory_azure_resources")

    def test_powerplatform_routes(self) -> None:
        envs = self.router.route("list the power platform environments")
        self.assertEqual(envs["operation"], "discover_powerplatform_environments")
        detail = self.router.route(f"describe environment {ENV_ID}")
        self.assertEqual(detail["operation"], "describe_powerplatform_environment")
        self.assertEqual(detail["entities"]["environment_ids"], [ENV_ID])
        catalog = self.router.route("show power automate flows and connections")
        self.assertEqual(catalog["operation"], "list_powerplatform_catalog")

    def test_other_capabilities(self) -> None:
        cases = {
            "check cross platform coverage gaps": "correlate_cross_platform",
            "run a full scan of all clouds": "run_cloud_orchestration",
            "any inactive or stale resources?": "cloud_health_report",
            "build an executive report": "build_executive_report",
            "show the audit and governance policy": "governance_summary",
            "check my sign in identity profiles": "get_unified_identity_health",
        }
        for text, operation in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.router.route(text)["operation"], operation)

    def test_mutating_request_requires_confirmation(self) -> None:
        result = self.router.route(f"delete the power platform environment {ENV_ID}")
        self.assertEqual(result["intent"], "controlled_operation")
        self.assertTrue(result["requires_confirmation"])
        self.assertFalse(result["executable"])
        self.assertIsNone(result["operation"])

    def test_token_like_input_is_redacted(self) -> None:
        result = self.router.route(f"check identity with Bearer {TOKEN}")
        self.assertNotIn(TOKEN, str(result))
        self.assertTrue(result["redaction_applied"])

    def test_unknown_and_empty_utterances(self) -> None:
        for text in ("hello", "", None, 123):
            with self.subTest(text=text):
                result = self.router.route(text)
                self.assertEqual(result["intent"], "clarify")
                self.assertFalse(result["executable"])

    def test_router_never_executes_and_catalogue_is_read_only(self) -> None:
        for text in ("list environments", "delete everything", "random"):
            self.assertFalse(self.router.route(text)["executable"])
        self.assertTrue(all(item["read_only"] for item in self.router.describe_intents()))


if __name__ == "__main__":
    unittest.main()
