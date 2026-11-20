"""Reporting and analytics (v1.1 Module 8).

Pure stdlib serialization and aggregation over already-collected cloud records.
No network, no file writes, no credentials. Every output is recursively
redacted so tokens/keys never reach a report.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from typing import Any

_SENSITIVE_WORDS = (
    "token", "secret", "password", "credential", "authorization", "connectionstring",
)
_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._\-+/=]{8,}", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[A-Za-z0-9._\-]{12,}")
_REDACTED = "[REDACTED]"


class CloudReportingService:
    """Deterministic, secret-safe reporting helpers."""

    @staticmethod
    def redact(value: Any) -> Any:
        """Recursively redact sensitive keys and token-like values (idempotent)."""
        if isinstance(value, dict):
            return {
                key: _REDACTED if CloudReportingService._sensitive_key(key)
                else CloudReportingService.redact(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [CloudReportingService.redact(item) for item in value]
        if isinstance(value, str):
            cleaned = _BEARER.sub(f"Bearer {_REDACTED}", value)
            return _JWT.sub(_REDACTED, cleaned)
        return value

    @staticmethod
    def _sensitive_key(name: Any) -> bool:
        lower = str(name).lower()
        if any(word in lower for word in _SENSITIVE_WORDS):
            return True
        return "key" in set(re.split(r"[^a-z0-9]+", lower))

    def to_json(self, data: Any) -> str:
        return json.dumps(
            self.redact(data), indent=2, ensure_ascii=False, default=str, sort_keys=True
        )

    def to_markdown(self, title: str, sections: Any) -> str:
        lines = [f"# {str(title or 'Report').strip()}", ""]
        if not isinstance(sections, dict):
            return "\n".join(lines)
        for heading, content in sections.items():
            lines.extend([f"## {heading}", ""])
            if isinstance(content, (list, tuple)):
                dict_rows = [row for row in content if isinstance(row, dict)]
                if dict_rows and len(dict_rows) == len(content):
                    columns = list(dict_rows[0].keys())
                    lines.append("| " + " | ".join(columns) + " |")
                    lines.append("| " + " | ".join("---" for _ in columns) + " |")
                    for row in dict_rows:
                        safe_row = self.redact(row)
                        cells = [
                            str(safe_row.get(column, "")).replace("|", "\\|")
                            for column in columns
                        ]
                        lines.append("| " + " | ".join(cells) + " |")
                else:
                    for item in content:
                        lines.append(f"- {self.redact(item)}")
            else:
                lines.append(str(self.redact(content)))
            lines.append("")
        return "\n".join(lines)

    def to_csv(self, rows: Any, columns: Any = None) -> str:
        clean = [row for row in rows if isinstance(row, dict)] if isinstance(rows, (list, tuple)) else []
        if not clean:
            return ""
        fields = [str(column) for column in columns] if isinstance(columns, (list, tuple)) else list(clean[0].keys())
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in clean:
            safe_row = self.redact(row)
            writer.writerow({field: safe_row.get(field, "") for field in fields})
        return buffer.getvalue()

    def aggregate_counts(self, items: Any, field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in items if isinstance(items, (list, tuple)) else ():
            if not isinstance(row, dict):
                continue
            value = str(row.get(field) or "unknown")
            counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items()))

    def build_executive_report(
        self,
        azure_overview: Any,
        pp_environments: Any,
        extra: Any = None,
    ) -> dict[str, Any]:
        safe_azure = self.redact(azure_overview)
        safe_pp = self.redact(pp_environments)
        safe_extra = self.redact(extra or {})
        env_rows = safe_pp if isinstance(safe_pp, list) else []
        subscriptions = safe_azure.get("subscriptions", []) if isinstance(safe_azure, dict) else []
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "counts": {
                "azure_subscriptions": len(subscriptions) if isinstance(subscriptions, list) else 0,
                "powerplatform_environments": len(env_rows) if isinstance(env_rows, list) else 0,
            },
            "highlights": [
                f"{len(env_rows)} Power Platform environments discovered",
                f"{len(subscriptions) if isinstance(subscriptions, list) else 0} Azure subscriptions discovered",
            ],
            "extra": safe_extra,
            "token_material_returned": False,
        }
        report["markdown"] = self.to_markdown("SKYFALL Executive Cloud Report", {
            "Summary": report["highlights"],
            "Environments": env_rows if env_rows else ["No environments discovered"],
        })
        return report
