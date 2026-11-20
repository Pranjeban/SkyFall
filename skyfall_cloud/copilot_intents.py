"""Universal Copilot natural-language routing (v1.1 Module 1).

A deterministic intent router mapping user utterances to the read-only SKYFALL
capabilities. It NEVER executes anything: every result carries
``executable: False`` and mutating requests require explicit confirmation and
the controlled-operations gate. Token-like strings are redacted before any
matching or entity extraction.
"""

from __future__ import annotations

import re
from typing import Any

_GUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_TOKENLIKE = re.compile(
    r"\beyJ[A-Za-z0-9._\-]{12,}|Bearer\s+[A-Za-z0-9._\-+/=]{8,}", re.IGNORECASE
)
_HARD_MUTATING = (
    "delete", "remove", "destroy", "disable", "enable", "restart", "stop",
    "start", "modify", "update", "create", "write", "deploy", "execute",
    "grant", "revoke", "reset", "publish", "kill", "purge", "drop",
)
_SOFT_MUTATING = ("run", "set")

# (intent, provider, operation, keywords)
INTENT_PATTERNS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("identity_health", "identity", "get_unified_identity_health",
     ("identity", "sign in", "signed in", "auth", "profile", "msal", "tenant login")),
    ("azure_footprint", "azure", "discover_azure_footprint",
     ("azure tenant", "azure subscription", "azure footprint", "management group", "azure account")),
    ("azure_inventory", "azure", "inventory_azure_resources",
     ("inventory", "resource graph", "virtual machine", "function app", "azure resource")),
    ("pp_environments", "powerplatform", "discover_powerplatform_environments",
     ("power platform environment", "dataverse environment", "pp environment", "list environments")),
    ("pp_environment_detail", "powerplatform", "describe_powerplatform_environment",
     ("inspect environment", "environment detail", "describe environment", "security flag")),
    ("pp_catalog", "powerplatform", "list_powerplatform_catalog",
     ("flow", "power automate", "canvas app", "solution", "connection")),
    ("cross_platform", "both", "correlate_cross_platform",
     ("cross platform", "both platforms", "coverage gap", "dependency map", "unified inventory")),
    ("orchestration", "both", "run_cloud_orchestration",
     ("full scan", "full report", "orchestrat", "investigate", "all clouds")),
    ("monitoring", "both", "cloud_health_report",
     ("anomal", "inactive", "stale", "monitor", "health report", "broken connection")),
    ("reporting", "both", "build_executive_report",
     ("report", "summary", "analytics", "export", "executive")),
    ("governance", "both", "governance_summary",
     ("audit", "governance", "policy", "compliance", "who accessed")),
)


class CopilotIntentRouter:
    """Map utterances to capabilities without performing any operation."""

    @staticmethod
    def _clean(utterance: Any) -> str:
        text = str(utterance or "")
        return _TOKENLIKE.sub("[REDACTED]", text).strip()

    @staticmethod
    def _has_verb(text: str, verbs: tuple[str, ...]) -> bool:
        lowered = text.lower()
        return any(re.search(rf"\b{re.escape(verb)}\b", lowered) for verb in verbs)

    def _mutating_result(self, entities: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "intent": "controlled_operation",
            "provider": None,
            "operation": None,
            "confidence": 1.0,
            "requires_confirmation": True,
            "executable": False,
            "entities": entities,
            "reason": (
                "Mutating requests require explicit approval through the "
                "controlled operations gate; this router never executes them."
            ),
        }

    def route(self, utterance: Any) -> dict[str, Any]:
        raw = str(utterance or "")
        text = self._clean(utterance)
        lowered = text.lower()
        entities = {
            "environment_ids": _GUID.findall(text),
            "raw_length": len(text),
        }
        redaction_applied = text != raw.strip()
        if not text:
            return self._clarify("No request was supplied.")

        if self._has_verb(text, _HARD_MUTATING):
            return {**self._mutating_result(entities), "redaction_applied": redaction_applied}

        best: tuple[int, tuple[str, str, str, tuple[str, ...]]] | None = None
        for pattern in INTENT_PATTERNS:
            score = sum(1 for keyword in pattern[3] if keyword in lowered)
            if score and (best is None or score > best[0]):
                best = (score, pattern)
        if best is None:
            if self._has_verb(text, _SOFT_MUTATING):
                return {**self._mutating_result(entities), "redaction_applied": redaction_applied}
            return self._clarify("No matching read-only capability was identified.", entities)
        score, (intent, provider, operation, _keywords) = best
        return {
            "success": True,
            "intent": intent,
            "provider": provider,
            "operation": operation,
            "confidence": min(1.0, 0.5 + 0.15 * score),
            "requires_confirmation": False,
            "executable": False,
            "entities": entities,
            "redaction_applied": redaction_applied,
            "reason": "Read-only intent routed; execution requires an explicit tool call.",
        }

    @staticmethod
    def _clarify(reason: str, entities: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "success": False,
            "intent": "clarify",
            "provider": None,
            "operation": None,
            "confidence": 0.0,
            "requires_confirmation": False,
            "executable": False,
            "entities": entities or {},
            "reason": reason,
        }

    @staticmethod
    def describe_intents() -> list[dict[str, Any]]:
        return [
            {"intent": intent, "provider": provider, "operation": operation,
             "keywords": list(keywords), "read_only": True}
            for intent, provider, operation, keywords in INTENT_PATTERNS
        ]
