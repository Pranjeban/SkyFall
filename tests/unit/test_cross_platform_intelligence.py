"""Unit tests for offline cross-platform inventory correlation."""

from __future__ import annotations

import unittest

from skyfall_cloud.cross_platform_intelligence import CrossPlatformIntelligence


class CrossPlatformIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = CrossPlatformIntelligence()
        self.azure = [
            {"id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Web/sites/Shared",
             "name": "Shared", "type": "Microsoft.Web/sites", "tags": {"app": "shared"}},
            {"id": "azure-2", "name": "Azure Only", "type": "Microsoft.Sql/servers"},
        ]
        self.pp = [
            {"environmentId": "{env-1}", "displayName": "Shared",
             "state": "Ready", "access_token": "must-not-leak"},
            {"environmentId": "env-2", "displayName": "PP Only", "state": "Ready"},
        ]

    def test_unified_inventory_counts_and_source_tags(self) -> None:
        result = self.engine.unified_inventory(
            self.azure, self.pp, [{"name": "App"}], [{"name": "Flow"}]
        )
        self.assertEqual(
            result["counts"],
            {"azure": 2, "pp_environments": 2, "pp_apps": 1, "pp_flows": 1},
        )
        self.assertEqual(result["count"], 6)
        self.assertEqual(
            [item["source"] for item in result["items"]],
            ["azure", "azure", "pp_environment", "pp_environment", "pp_app", "pp_flow"],
        )

    def test_malformed_entries_are_skipped(self) -> None:
        result = self.engine.unified_inventory(
            [None, "bad", 7, {"name": "Good"}], {"bad": "row"}, None, "nope"
        )
        self.assertEqual(result["items"], [{"source": "azure", "name": "Good"}])
        self.assertEqual(result["counts"]["pp_environments"], 0)

    def test_map_dependencies_matches_name_id_tag_and_connections(self) -> None:
        result = self.engine.map_dependencies(
            self.azure, self.pp,
            [{"source": "Azure Only", "target": "env-2"}],
        )
        reasons = {edge["match"] for edge in result["edges"]}
        self.assertTrue({"name", "connection"}.issubset(reasons))
        self.assertTrue(all(edge["source"] and edge["target"] for edge in result["edges"]))
        self.assertEqual(result["count"], len(result["edges"]))

    def test_map_dependencies_is_deterministic(self) -> None:
        first = self.engine.map_dependencies(self.azure, self.pp)
        second = self.engine.map_dependencies(self.azure, self.pp)
        self.assertEqual(first, second)

    def test_coverage_gaps_both_directions(self) -> None:
        gaps = self.engine.find_coverage_gaps(self.azure, self.pp)
        self.assertEqual([i["name"] for i in gaps["azure_only"]], ["Azure Only"])
        self.assertEqual([i["name"] for i in gaps["pp_only"]], ["PP Only"])
        self.assertEqual(gaps["counts"], {"azure_only": 1, "pp_only": 1})

    def test_compare_postures_buckets(self) -> None:
        result = self.engine.compare_postures(self.azure, self.pp)
        self.assertEqual(result["common"], ["Shared"])
        self.assertEqual(result["only_azure"], ["Azure Only"])
        self.assertEqual(result["only_pp"], ["PP Only"])
        self.assertEqual(result["counts"], {"common": 1, "only_azure": 1, "only_pp": 1})

    def test_compare_postures_custom_key_and_bad_shapes(self) -> None:
        result = self.engine.compare_postures(
            [{"name": "a", "state": "Ready"}, None],
            [{"name": "b", "state": "Ready"}, "x"],
            key="state",
        )
        self.assertEqual(result["common"], ["Ready"])
        self.assertEqual(result["only_azure"], [])
        self.assertEqual(result["only_pp"], [])
        self.assertEqual(
            self.engine.compare_postures(self.azure, self.pp, key="access_token")["key"],
            "name",
        )

    def test_summarize_digest_and_secret_redaction(self) -> None:
        digest = self.engine.summarize(self.azure, self.pp)
        self.assertEqual(digest["total_items"], 4)
        self.assertEqual(digest["coverage_gap_count"], 2)
        self.assertEqual(len(digest["top_gaps"]), 2)
        inventory = self.engine.unified_inventory(self.azure, self.pp)
        self.assertNotIn("access_token", str(inventory))
        self.assertNotIn("must-not-leak", str(digest))

    def test_empty_and_unexpected_inputs(self) -> None:
        for value in (None, 0, "x", {"a": 1}, []):
            self.assertEqual(self.engine.unified_inventory(value, value)["count"], 0)
            self.assertEqual(self.engine.map_dependencies(value, value)["edges"], [])
            self.assertEqual(self.engine.find_coverage_gaps(value, value)["count"], 0)
            self.assertEqual(self.engine.summarize(value, value)["total_items"], 0)


if __name__ == "__main__":
    unittest.main()
