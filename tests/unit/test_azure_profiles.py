from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skyfall_cloud.azure_profiles import AzureProfileManager, AzureProfileStore
from skyfall_cloud.command_runner import CommandResult


class AzureProfileTests(unittest.TestCase):
    def test_default_profile_is_always_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = AzureProfileStore(Path(temp) / "profiles")
            profiles = store.list_profiles()
            self.assertEqual(len(profiles), 1)
            self.assertEqual(profiles[0]["profile_id"], "azure-cli-default")

    def test_create_profile_uses_an_isolated_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = AzureProfileStore(Path(temp) / "profiles")
            profile = store.create_profile("Company QA", "11111111-1111-1111-1111-111111111111")
            self.assertTrue(Path(profile["config_dir"]).is_dir())
            login_command = store.login_command(profile)
            self.assertIn("AZURE_CONFIG_DIR", login_command)
            self.assertIn("core.enable_broker_on_windows=false", login_command)
            self.assertIn("--tenant", login_command)
            self.assertNotIn("--use-device-code", login_command)
            self.assertIn("11111111-1111-1111-1111-111111111111", login_command)
            persisted = store.registry_path.read_text(encoding="utf-8")
            self.assertNotIn("access_token", persisted.lower())
            self.assertNotIn("refresh_token", persisted.lower())


    def test_profile_registry_rejects_config_directory_outside_managed_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "profiles"
            root.mkdir()
            store = AzureProfileStore(root)
            store.registry_path.write_text(json.dumps({
                "schema_version": 1,
                "profiles": [{
                    "profile_id": "unexpected-profile",
                    "name": "External",
                    "config_dir": str(Path(temp) / "outside"),
                }],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside SKYFALL"):
                store.list_profiles()

    def test_duplicate_profile_name_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = AzureProfileStore(Path(temp) / "profiles")
            store.create_profile("Company QA", "contoso.onmicrosoft.com")
            with self.assertRaisesRegex(ValueError, "already exists"):
                store.create_profile("company qa", "contoso.onmicrosoft.com")

    def test_subscription_list_returns_safe_fields(self) -> None:
        def fake_runner(executable, args, **kwargs):
            self.assertEqual(executable, "az")
            if args[:2] == ["account", "list"]:
                return CommandResult(
                    executable="az", returncode=0,
                    stdout=json.dumps([{
                        "id": "sub-1", "name": "QA Subscription", "tenantId": "tenant-1",
                        "state": "Enabled", "isDefault": True,
                        "user": {"name": "engineer@example.com", "type": "user"},
                        "accessToken": "SHOULD_NOT_APPEAR",
                    }]), stderr="",
                )
            if args[:2] == ["account", "show"]:
                return CommandResult(
                    executable="az", returncode=0,
                    stdout=json.dumps({"tenantId": "tenant-1", "id": "sub-1", "name": "QA Subscription", "user": {"name": "engineer@example.com", "type": "user"}}),
                    stderr="",
                )
            raise AssertionError(args)

        with tempfile.TemporaryDirectory() as temp:
            manager = AzureProfileManager(AzureProfileStore(Path(temp) / "profiles"), runner=fake_runner)
            result = manager.list_subscriptions()
            self.assertTrue(result["success"])
            self.assertEqual(result["count"], 1)
            self.assertEqual(result["subscriptions"][0]["profile"], "Default Azure CLI")
            self.assertEqual(result["subscriptions"][0]["profile_id"], "azure-cli-default")
            serialized = json.dumps(result)
            self.assertNotIn("SHOULD_NOT_APPEAR", serialized)
            self.assertNotIn("accessToken", serialized)

    def test_tenants_are_deduplicated_from_subscription_cache(self) -> None:
        def fake_runner(executable, args, **kwargs):
            if args[:2] == ["account", "list"]:
                payload = [
                    {"id": "s1", "name": "One", "tenantId": "t1"},
                    {"id": "s2", "name": "Two", "tenantId": "t1"},
                    {"id": "s3", "name": "Three", "tenantId": "t2"},
                ]
                return CommandResult("az", 0, json.dumps(payload), "")
            if args[:2] == ["account", "show"]:
                return CommandResult("az", 0, json.dumps({"tenantId": "t2"}), "")
            raise AssertionError(args)

        with tempfile.TemporaryDirectory() as temp:
            manager = AzureProfileManager(AzureProfileStore(Path(temp) / "profiles"), runner=fake_runner)
            result = manager.list_tenants()
            self.assertTrue(result["success"])
            self.assertEqual(result["count"], 2)
            self.assertEqual({x["tenant_id"] for x in result["tenants"]}, {"t1", "t2"})


    def test_all_profiles_aggregate_subscriptions_with_profile_identity(self) -> None:
        def fake_runner(executable, args, **kwargs):
            config_dir = (kwargs.get("env_overrides") or {}).get("AZURE_CONFIG_DIR")
            profile_name = "Isolated Account" if config_dir else "Default Azure CLI"
            sub_id = "sub-isolated" if config_dir else "sub-default"
            return CommandResult(
                executable="az", returncode=0,
                stdout=json.dumps([{
                    "id": sub_id, "name": f"{profile_name} subscription", "tenantId": f"tenant-{sub_id}",
                    "state": "Enabled", "isDefault": False,
                    "user": {"name": f"{profile_name.lower().replace(' ', '')}@example.com"},
                }]), stderr="",
            )

        with tempfile.TemporaryDirectory() as temp:
            store = AzureProfileStore(Path(temp) / "profiles")
            store.create_profile("Isolated Account", "contoso.onmicrosoft.com")
            manager = AzureProfileManager(store, runner=fake_runner)
            result = manager.list_subscriptions("all")
            self.assertTrue(result["success"])
            self.assertEqual(result["count"], 2)
            self.assertEqual({item["subscription_id"] for item in result["subscriptions"]}, {"sub-default", "sub-isolated"})
            self.assertEqual({item["profile_id"] for item in result["subscriptions"]}, {"azure-cli-default", store.list_profiles()[1]["profile_id"]})

    def test_custom_profile_is_passed_through_azure_config_dir(self) -> None:
        captured = {}

        def fake_runner(executable, args, **kwargs):
            captured.update(kwargs.get("env_overrides", {}))
            return CommandResult("az", 0, json.dumps({"tenantId": "tenant-a", "id": "sub-a", "name": "Dev", "user": {"name": "user@example.com"}}), "")

        with tempfile.TemporaryDirectory() as temp:
            store = AzureProfileStore(Path(temp) / "profiles")
            profile = store.create_profile("Isolated QA", "contoso.onmicrosoft.com")
            manager = AzureProfileManager(store, runner=fake_runner)
            result = manager.get_auth_status(profile["profile_id"])
            self.assertTrue(result["authenticated"])
            self.assertEqual(captured["AZURE_CONFIG_DIR"], profile["config_dir"])

    def test_create_profile_requires_a_valid_tenant(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = AzureProfileStore(Path(temp) / "profiles")
            with self.assertRaisesRegex(ValueError, "tenant ID or tenant domain"):
                store.create_profile("Company QA", "")
            with self.assertRaisesRegex(ValueError, "Tenant must be a GUID"):
                store.create_profile("Company QA", "not a tenant")

    def test_login_profile_uses_isolated_browser_flow_and_auto_discovers(self) -> None:
        calls = []

        def fake_runner(executable, args, **kwargs):
            calls.append((executable, list(args), dict(kwargs.get("env_overrides") or {})))
            if args[:2] == ["account", "show"]:
                return CommandResult("az", 0, json.dumps({
                    "tenantId": "tenant-a", "id": "sub-a", "name": "QA Subscription",
                    "user": {"name": "engineer@example.com", "type": "user"},
                }), "")
            if args[:2] == ["account", "list"]:
                return CommandResult("az", 0, json.dumps([{
                    "id": "sub-a", "name": "QA Subscription", "tenantId": "tenant-a",
                    "state": "Enabled", "isDefault": True,
                    "user": {"name": "engineer@example.com", "type": "user"},
                }]), "")
            return CommandResult("az", 0, "{}", "")

        with tempfile.TemporaryDirectory() as temp:
            store = AzureProfileStore(Path(temp) / "profiles")
            profile = store.create_profile("Company QA", "tenant-a.onmicrosoft.com")
            manager = AzureProfileManager(store, runner=fake_runner)
            result = manager.login_profile(profile["profile_id"])
            self.assertTrue(result["success"])
            self.assertEqual(result["subscriptions"]["count"], 1)
            self.assertEqual(result["tenants"]["count"], 1)  # configured domain resolves to canonical tenant ID
            login_calls = [call for call in calls if call[1] and call[1][0] == "login"]
            self.assertEqual(len(login_calls), 1)
            self.assertIn("--tenant", login_calls[0][1])
            self.assertNotIn("--use-device-code", login_calls[0][1])
            self.assertEqual(login_calls[0][2]["AZURE_CONFIG_DIR"], profile["config_dir"])
            settings = [call for call in calls if call[1][:2] == ["config", "set"]]
            self.assertEqual(len(settings), 2)


    def test_configured_tenant_domain_is_not_reported_as_duplicate_tenant_id(self) -> None:
        def fake_runner(executable, args, **kwargs):
            if args[:2] == ["account", "list"]:
                return CommandResult("az", 0, json.dumps([{
                    "id": "sub-1", "name": "QA", "tenantId": "11111111-1111-1111-1111-111111111111"
                }]), "")
            if args[:2] == ["account", "show"]:
                return CommandResult("az", 0, json.dumps({
                    "tenantId": "11111111-1111-1111-1111-111111111111"
                }), "")
            raise AssertionError(args)

        with tempfile.TemporaryDirectory() as temp:
            store = AzureProfileStore(Path(temp) / "profiles")
            profile = store.create_profile("Company QA", "contoso.onmicrosoft.com")
            result = AzureProfileManager(store, runner=fake_runner).list_tenants(profile["profile_id"])
            self.assertTrue(result["success"])
            self.assertEqual(result["count"], 1)
            self.assertEqual(result["tenants"][0]["tenant_id"], "11111111-1111-1111-1111-111111111111")
            self.assertEqual(result["configured_tenant_hint"], "contoso.onmicrosoft.com")

    def test_default_azure_cli_profile_is_not_logged_in_by_skyfall(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manager = AzureProfileManager(AzureProfileStore(Path(temp) / "profiles"), runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not execute")))
            with self.assertRaisesRegex(ValueError, "does not sign in through the Default Azure CLI"):
                manager.login_profile("azure-cli-default")

    def test_unauthenticated_azure_cli_message_is_friendly_not_raw_cli_error(self) -> None:
        def fake_runner(executable, args, **kwargs):
            return CommandResult(
                "az", 1, "", "ERROR: Please run 'az login' to setup account."
            )

        with tempfile.TemporaryDirectory() as temp:
            manager = AzureProfileManager(AzureProfileStore(Path(temp) / "profiles"), runner=fake_runner)
            status = manager.get_auth_status("azure-cli-default")
            self.assertFalse(status["authenticated"])
            self.assertIn("not signed in", status["error"].lower())
            self.assertNotIn("Please run 'az login'", status["error"])

    def test_unauthenticated_subscription_error_is_normalized(self) -> None:
        def fake_runner(executable, args, **kwargs):
            return CommandResult(
                "az", 1, "", "ERROR: Please run 'az login' to setup account."
            )

        with tempfile.TemporaryDirectory() as temp:
            manager = AzureProfileManager(AzureProfileStore(Path(temp) / "profiles"), runner=fake_runner)
            result = manager.list_subscriptions("azure-cli-default")
            self.assertFalse(result["success"])
            self.assertIn("not signed in", result["error"].lower())
            self.assertNotIn("Please run 'az login'", result["error"])


if __name__ == "__main__":
    unittest.main()
