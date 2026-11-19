"""Read-only monitoring and anomaly detection MCP tools."""

from __future__ import annotations

import json
from typing import Any

from skyfall_cloud.monitoring import (
    AzureResourceHealthChecker,
    FunctionAppAvailabilityChecker,
    InactiveResourceDetector,
    PowerAutomateFailureDetector,
)


def check_azure_resource_health(profile_id: str = "all") -> str:
    checker = AzureResourceHealthChecker()
    payload = checker.check(profile_id=profile_id)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def check_function_app_availability(profile_id: str = "all") -> str:
    checker = FunctionAppAvailabilityChecker()
    payload = checker.check(profile_id=profile_id)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def detect_power_automate_failures(environment_id: str = "") -> str:
    detector = PowerAutomateFailureDetector()
    payload = detector.detect(environment_id=environment_id)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def detect_inactive_resources(inactive_days: int = 30) -> str:
    detector = InactiveResourceDetector(inactive_days=inactive_days)
    payload = detector.detect(inactive_days=inactive_days)
    return json.dumps(payload, ensure_ascii=False, indent=2)
