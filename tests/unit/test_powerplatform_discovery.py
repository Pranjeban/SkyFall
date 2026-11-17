from __future__ import annotations

import json
import unittest

from skyfall_cloud.command_runner import CommandResult
from skyfall_cloud.powerplatform import (
    PowerPlatformDiscovery, parse_pac_auth_profiles,
    parse_pac_admin_environment_table, _decode_json_output,
)


class PowerPlatformDiscoveryTests(unittest.TestCase):
    def test_parse_documented_pac_auth_table(self) -> None:
        sample = """Index Active Kind      Name Friendly Name                   Url                                 User                                     Cloud  Type
[1]   *      UNIVERSAL      Company QA                       https://qa.crm.dynamics.com/        engineer@example.com                   Public User
[2]          UNIVERSAL      Company PROD                     https://prod.crm.dynamics.com/      engineer@example.com                   Public User
"""
        profiles = parse_pac_auth_profiles(sample)
        self.assertEqual(len(profiles), 2)
        self.assertTrue(profiles[0]["active"])
        self.assertEqual(profiles[0]["index"], 1)
        self.assertEqual(profiles[0]["environment_url"], "https://qa.crm.dynamics.com")
        self.assertEqual(profiles[0]["user"], "engineer@example.com")

    def test_list_environments_uses_active_profile_without_switching(self) -> None:
        calls = []
        def fake_runner(executable, args, **kwargs):
            calls.append((executable, list(args)))
            if args == ["auth", "list"]:
                return CommandResult("pac", 0, "Index Active Kind Name Friendly Name Url User Cloud Type\n[1] * UNIVERSAL QA https://qa.crm.dynamics.com/ engineer@example.com Public User\n", "")
            if args == ["admin", "list", "--json"]:
                return CommandResult("pac", 0, json.dumps([{"EnvironmentId":"env-1","DisplayName":"QA","EnvironmentUrl":"https://qa.crm.dynamics.com","EnvironmentType":"Sandbox","OrganizationId":"org-1"}]), "")
            raise AssertionError(args)
        discovery = PowerPlatformDiscovery(runner=fake_runner)
        result = discovery.list_environments()
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["environments"][0]["name"], "QA")
        self.assertNotIn("select", " ".join(arg for _, args in calls for arg in args))

    def test_environment_discovery_fails_clearly_without_active_profile(self) -> None:
        def fake_runner(executable, args, **kwargs):
            return CommandResult("pac", 0, "No authentication profiles found.", "")
        result = PowerPlatformDiscovery(runner=fake_runner).list_environments()
        self.assertFalse(result["success"])
        self.assertIn("No active PAC CLI", result["error"])


    def test_environment_discovery_falls_back_to_documented_table_output(self) -> None:
        calls = []
        table = (
            "Environment   Environment Id                        Environment Url                        Type        Organization Id\n"
            "Contoso QA    00000000-0000-0000-0000-000000000001  https://contoso-qa.crm.dynamics.com/   Sandbox     11111111-1111-1111-1111-111111111111\n"
            "Contoso PROD  00000000-0000-0000-0000-000000000002  https://contoso.crm.dynamics.com/      Production  11111111-1111-1111-1111-111111111111\n"
        )

        def fake_runner(executable, args, **kwargs):
            calls.append(list(args))
            if args == ["auth", "list"]:
                return CommandResult("pac", 0, "Index Active Kind Name Friendly Name Url User Cloud Type\n[1] * UNIVERSAL Company QA https://contoso-qa.crm.dynamics.com/ engineer@example.com Public User\n", "")
            if args == ["admin", "list", "--json"]:
                return CommandResult("pac", 0, "PAC CLI information banner; JSON output unavailable", "")
            if args == ["admin", "list"]:
                return CommandResult("pac", 0, table, "")
            raise AssertionError(args)

        result = PowerPlatformDiscovery(runner=fake_runner).list_environments()
        self.assertTrue(result["success"])
        self.assertEqual(result["discovery_format"], "table_fallback")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["environments"][0]["name"], "Contoso QA")
        self.assertEqual(result["environments"][1]["type"], "Production")
        self.assertEqual(calls[-2:], [["admin", "list", "--json"], ["admin", "list"]])

    def test_environment_table_parser_preserves_names_with_spaces(self) -> None:
        table = (
            "Environment                 Environment Id                        Environment Url                        Type        Organization Id\n"
            "Long Display Name - QA       00000000-0000-0000-0000-000000000001  https://long-qa.crm.dynamics.com/     Sandbox     11111111-1111-1111-1111-111111111111\n"
        )
        rows = parse_pac_admin_environment_table(table)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Long Display Name - QA")
        self.assertEqual(rows[0]["environment_id"], "00000000-0000-0000-0000-000000000001")

    def test_environment_discovery_combined_json_handles_bom_ansi_and_preamble(self) -> None:
        payload = _decode_json_output('\ufeffINFO: environments follow\n\x1b[32m[{"EnvironmentId":"env-1","DisplayName":"QA"}]\x1b[0m')
        self.assertEqual(payload[0]["EnvironmentId"], "env-1")

    def test_environment_discovery_returns_friendly_error_when_both_formats_are_unusable(self) -> None:
        def fake_runner(executable, args, **kwargs):
            if args == ["auth", "list"]:
                return CommandResult("pac", 0, "Index Active Kind Name Friendly Name Url User Cloud Type\n[1] * UNIVERSAL QA https://qa.crm.dynamics.com/ engineer@example.com Public User\n", "")
            if args == ["admin", "list", "--json"]:
                return CommandResult("pac", 0, "unrecognized output", "")
            if args == ["admin", "list"]:
                return CommandResult("pac", 0, "unrecognized table output", "")
            raise AssertionError(args)
        result = PowerPlatformDiscovery(runner=fake_runner).list_environments()
        self.assertFalse(result["success"])
        self.assertEqual(result["diagnostic_code"], "environment_list_format_unrecognized")
        self.assertIn("Both JSON and standard table formats were attempted", result["error"])
        self.assertNotIn("unrecognized table output", result["error"])

    def test_create_profile_starts_normal_interactive_login_and_discovers_environments(self) -> None:
        calls = []
        auth_table = (
            "Index Active Kind Name Friendly Name Url User Cloud Type\n"
            "[1]   *      UNIVERSAL Company QA https://qa.crm.dynamics.com/ engineer@example.com Public User\n"
        )

        created = {"value": False}

        def fake_runner(executable, args, **kwargs):
            calls.append((executable, list(args)))
            if args == ["auth", "list"]:
                return CommandResult("pac", 0, auth_table if created["value"] else "No authentication profiles found.", "")
            if args[:2] == ["auth", "create"]:
                created["value"] = True
                return CommandResult("pac", 0, "Authentication profile created.", "")
            if args == ["admin", "list", "--json"]:
                return CommandResult("pac", 0, json.dumps([{
                    "EnvironmentId": "env-qa",
                    "DisplayName": "QA",
                    "EnvironmentUrl": "https://qa.crm.dynamics.com",
                    "EnvironmentType": "Sandbox",
                    "OrganizationId": "org-qa",
                    "TenantId": "tenant-qa",
                }]), "")
            raise AssertionError(args)

        result = PowerPlatformDiscovery(runner=fake_runner).create_profile_and_login(
            "Company QA", "https://qa.crm.dynamics.com"
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["auth"]["authenticated"])
        self.assertEqual(result["environments"]["count"], 1)
        create_args = next(args for _, args in calls if args[:2] == ["auth", "create"])
        self.assertEqual(create_args, ["auth", "create", "--name", "Company QA", "--environment", "https://qa.crm.dynamics.com"])
        self.assertNotIn("--deviceCode", create_args)
        self.assertNotIn("--tenant", create_args)

    def test_create_profile_rejects_invalid_name(self) -> None:
        discovery = PowerPlatformDiscovery(runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("runner must not be called")))
        with self.assertRaisesRegex(ValueError, "1 to 30"):
            discovery.create_profile_and_login("X" * 31)

    def test_select_profile_is_explicit_and_queries_selected_context(self) -> None:
        calls = []
        def fake_runner(executable, args, **kwargs):
            calls.append(list(args))
            if args == ["auth", "select", "--index", "2"]:
                return CommandResult("pac", 0, "Profile selected.", "")
            if args == ["auth", "list"]:
                table = "Index Active Kind Name Friendly Name Url User Cloud Type\n[2] * UNIVERSAL QA https://qa.crm.dynamics.com/ engineer@example.com Public User\n"
                return CommandResult("pac", 0, table, "")
            if args == ["admin", "list", "--json"]:
                return CommandResult("pac", 0, "[]", "")
            raise AssertionError(args)
        result = PowerPlatformDiscovery(runner=fake_runner).select_profile(2)
        self.assertTrue(result["success"])
        self.assertEqual(result["selected_index"], 2)
        self.assertEqual(calls[0], ["auth", "select", "--index", "2"])


if __name__ == "__main__":
    unittest.main()
