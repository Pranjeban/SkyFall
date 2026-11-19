"""SKYFALL desktop section registry (Phase 3/11 UI contract)."""

from __future__ import annotations

SECTIONS = [
    ("overview", "Overview", "Unified cloud status and operational summary"),
    ("copilot", "Copilot", "Natural-language interaction"),
    ("azure", "Azure Explorer", "Azure resource discovery and operations"),
    ("powerplatform", "Power Platform", "Environments, apps, flows and solutions"),
    ("engineering", "Engineering", "Scripts, repositories and workspaces"),
    ("orchestration", "Orchestration", "Plans, approvals and executions"),
    ("monitoring", "Monitoring", "Health, failures and anomalies"),
    ("reports", "Reports", "Excel, PDF and other artifacts"),
    ("identity", "Identity", "Accounts, tenants and profiles"),
    ("audit", "Audit", "Execution and operational history"),
    ("settings", "Settings", "Application configuration and policies"),
]


def section_keys() -> list[str]:
    return [s[0] for s in SECTIONS]


def section_by_key(key: str):
    for k, title, desc in SECTIONS:
        if k == key:
            return {"key": k, "title": title, "description": desc}
    return None
