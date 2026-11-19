"""Reporting & analytics (Phase 10)."""

from __future__ import annotations

import csv
import io
import json
from typing import Any


class ReportingService:
    def to_csv(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return buf.getvalue()

    def to_json(self, rows: list[dict[str, Any]]) -> str:
        return json.dumps(rows, indent=2, ensure_ascii=False, default=str)

    def to_markdown_table(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""
        cols = list(rows[0].keys())
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
        for row in rows:
            lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
        return "\n".join(lines)
