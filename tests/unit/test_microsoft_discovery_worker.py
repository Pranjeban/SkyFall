"""Characterization tests for the desktop Microsoft discovery worker."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from skyfall_cloud.worker import MicrosoftDiscoveryWorker


class _FakeInventory:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def find_function_apps_by_name(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return self.payload


class _Capture:
    def __init__(self) -> None:
        self.completed: list[tuple[str, dict]] = []
        self.failed: list[tuple[str, str]] = []

    def connect_completed(self, action: str, payload: dict) -> None:
        self.completed.append((action, payload))

    def connect_failed(self, action: str, error: str) -> None:
        self.failed.append((action, error))


def _run_lookup(payload: dict, *, name: str = "fn-qa-orders", profile_id: str = "azure-profile-1") -> tuple[_Capture, _FakeInventory]:
    capture = _Capture()
    fake = _FakeInventory(payload)
    worker = MicrosoftDiscoveryWorker(
        "azure_function_app_lookup",
        profile_id,
        params={"name": name, "exact": True},
    )
    worker.completed.connect(capture.connect_completed)
    worker.failed.connect(capture.connect_failed)
    with patch("skyfall_cloud.worker.AzureFunctionAppInventory", return_value=fake):
        worker.run()
    return capture, fake


class TestFunctionAppLookupWorker(unittest.TestCase):
    def test_successful_lookup_payload_is_preserved(self) -> None:
        payload = {
            "success": True,
            "status": "success",
            "match_count": 1,
            "matches": [{"name": "fn-qa-orders", "subscription": "QA"}],
            "summary": "Found 1 match for 'fn-qa-orders'.",
        }

        capture, fake = _run_lookup(payload)

        self.assertEqual(capture.failed, [])
        self.assertEqual(capture.completed, [("azure_function_app_lookup", payload)])
        self.assertEqual(
            fake.calls,
            [{"name": "fn-qa-orders", "profile_id": "azure-profile-1", "exact": True}],
        )

    def test_failed_discovery_payload_is_preserved_instead_of_generic_error(self) -> None:
        payload = {
            "success": False,
            "status": "blocked_test_mode",
            "matches": [],
            "match_count": 0,
            "summary": "Function App lookup is blocked while SKYFALL_TEST_MODE is enabled.",
        }

        capture, _ = _run_lookup(payload)

        self.assertEqual(capture.failed, [])
        self.assertEqual(capture.completed, [("azure_function_app_lookup", payload)])
        self.assertEqual(
            capture.completed[0][1]["summary"],
            "Function App lookup is blocked while SKYFALL_TEST_MODE is enabled.",
        )

    def test_invalid_name_still_reports_worker_failure(self) -> None:
        capture = _Capture()
        worker = MicrosoftDiscoveryWorker(
            "azure_function_app_lookup",
            "all",
            params={"name": "", "exact": True},
        )
        worker.completed.connect(capture.connect_completed)
        worker.failed.connect(capture.connect_failed)

        fake = MagicMock()
        fake.find_function_apps_by_name.side_effect = ValueError(
            "Function App name must be 1-200 visible characters."
        )
        with patch("skyfall_cloud.worker.AzureFunctionAppInventory", return_value=fake):
            worker.run()

        self.assertEqual(capture.completed, [])
        self.assertEqual(len(capture.failed), 1)
        self.assertEqual(capture.failed[0][0], "azure_function_app_lookup")
        self.assertIn("Function App name must be 1-200 visible characters.", capture.failed[0][1])


if __name__ == "__main__":
    unittest.main()
