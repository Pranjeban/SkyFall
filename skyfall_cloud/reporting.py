"""Shared helpers for safe, human-readable SKYFALL report files."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def filename_component(value: str, *, fallback: str = "General", max_length: int = 64) -> str:
    """Convert a label into a readable filename component without opaque IDs."""
    text = str(value or "").strip()
    text = re.sub(r"[._/\\]+", "-", text)
    text = re.sub(r"[^A-Za-z0-9-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        text = fallback
    return text[:max_length].strip("-") or fallback


def build_report_path(
    directory: str | Path,
    title_parts: Iterable[str],
    *,
    extension: str = ".xlsx",
    now: datetime | None = None,
) -> Path:
    """Build `Readable-Report-Scope-YYYY-MM-DD.xlsx` and avoid overwrites.

    If the same report is generated again on the same day, use `-02`, `-03`,
    etc. This keeps names readable while retaining previous deliverables.
    """
    folder = Path(directory).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    local_now = now or datetime.now().astimezone()
    components = [filename_component(part) for part in title_parts if str(part or "").strip()]
    if not components:
        components = ["SKYFALL-Report"]
    normalized_extension = extension if extension.startswith(".") else f".{extension}"
    stem = "-".join(components + [local_now.strftime("%Y-%m-%d")])
    candidate = folder / f"{stem}{normalized_extension}"
    sequence = 2
    while candidate.exists():
        candidate = folder / f"{stem}-{sequence:02d}{normalized_extension}"
        sequence += 1
    return candidate


def safe_excel_text(value: object) -> object:
    """Prevent untrusted text from being interpreted as an Excel formula."""
    if not isinstance(value, str):
        return value
    trimmed = value.lstrip(" \t\r\n")
    if trimmed.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


REPORT_SCHEMA_VERSION = "1.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _coerce_columns(columns, rows):
    if columns:
        result = []
        for item in columns:
            if isinstance(item, (tuple, list)):
                result.append(str(item[0]) if len(item) == 1 else str(item[1] if len(item) > 1 else item[0]))
            else:
                result.append(str(item))
        # If columns provided as (label, key) pairs, keep keys separately? We'll store labels.
        return result
    # infer
    if rows and isinstance(rows[0], dict):
        return [str(key) for key in rows[0].keys()]
    if rows and isinstance(rows[0], (list, tuple)):
        return [f"column_{index + 1}" for index in range(len(rows[0]))]
    return []


def _row_to_dict(row, columns):
    if isinstance(row, dict):
        # If columns are keys, select; otherwise all
        if columns and all(col in row for col in columns):
            return {col: row.get(col, "") for col in columns}
        return dict(row)
    if isinstance(row, (list, tuple)):
        values = list(row)
        if len(values) < len(columns):
            values.extend([""] * (len(columns) - len(values)))
        return {columns[i]: values[i] if i < len(values) else "" for i in range(len(columns))}
    return {"value": row}


def prepare_report(title="", rows=None, columns=None, metadata=None, summary=None):
    rows = list(rows or [])
    cols = _coerce_columns(columns, rows)
    normalized_rows = [_row_to_dict(row, cols) for row in rows]
    if not cols and normalized_rows:
        cols = list(normalized_rows[0].keys())
    # ensure all rows have same keys
    for row in normalized_rows:
        for col in cols:
            row.setdefault(col, "")
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "title": str(title or "SKYFALL Report"),
        "generated_at": _utc_now(),
        "columns": cols,
        "rows": normalized_rows,
        "metadata": dict(metadata or {}),
        "summary": dict(summary) if summary else {"row_count": len(normalized_rows)},
    }
    return report


# aliases
build_report = prepare_report
normalize_report = prepare_report
create_report = prepare_report


def _resolve_report(report=None, title="", rows=None, columns=None, metadata=None, summary=None):
    if isinstance(report, dict):
        # ensure schema
        if "columns" not in report:
            report = prepare_report(
                title=report.get("title", title),
                rows=report.get("rows", rows),
                columns=report.get("columns", columns),
                metadata=report.get("metadata", metadata),
                summary=report.get("summary", summary),
            )
        else:
            report.setdefault("schema_version", REPORT_SCHEMA_VERSION)
            report.setdefault("title", title or "SKYFALL Report")
            report.setdefault("generated_at", _utc_now())
            report.setdefault("metadata", metadata or {})
            report.setdefault("summary", summary or {"row_count": len(report.get("rows", []))})
        return report
    return prepare_report(title=title, rows=rows, columns=columns, metadata=metadata, summary=summary)


def write_csv_report(path, report=None, title="", rows=None, columns=None, metadata=None, summary=None, **kwargs):
    report = _resolve_report(report, title=title, rows=rows, columns=columns, metadata=metadata, summary=summary)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    import csv
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=report["columns"] or ["value"])
        writer.writeheader()
        for row in report["rows"]:
            writer.writerow({col: row.get(col, "") for col in (report["columns"] or ["value"])})
    return str(target)


def write_json_report(path, report=None, title="", rows=None, columns=None, metadata=None, summary=None, **kwargs):
    report = _resolve_report(report, title=title, rows=rows, columns=columns, metadata=metadata, summary=summary)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    target.write_text(_json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def write_markdown_report(path, report=None, title="", rows=None, columns=None, metadata=None, summary=None, **kwargs):
    report = _resolve_report(report, title=title, rows=rows, columns=columns, metadata=metadata, summary=summary)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {report['title']}", ""]
    lines.append(f"_Generated: {report['generated_at']}_")
    lines.append("")
    if report.get("metadata"):
        lines.append("## Metadata")
        lines.append("")
        lines.append("| Key | Value |")
        lines.append("| --- | --- |")
        for key, value in report["metadata"].items():
            lines.append(f"| {key} | {value} |")
        lines.append("")
    columns = report["columns"] or []
    if columns:
        lines.append("## Data")
        lines.append("")
        lines.append("| " + " | ".join(str(c) for c in columns) + " |")
        lines.append("| " + " | ".join("---" for _ in columns) + " |")
        for row in report["rows"]:
            values = [str(row.get(col, "")).replace("|", "\\|").replace("\n", " ") for col in columns]
            lines.append("| " + " | ".join(values) + " |")
        lines.append("")
    lines.append(f"_Rows: {len(report['rows'])}_")
    target.write_text("\n".join(lines), encoding="utf-8")
    return str(target)


def write_report(path, output_format="csv", **kwargs):
    fmt = str(output_format or "csv").lower().lstrip(".")
    if fmt in {"csv"}:
        return write_csv_report(path, **kwargs)
    if fmt in {"json"}:
        return write_json_report(path, **kwargs)
    if fmt in {"md", "markdown"}:
        return write_markdown_report(path, **kwargs)
    raise ValueError(f"Unsupported report format: {output_format}")


def generate_report(output_path, output_format="csv", **kwargs):
    # If output_path is a directory, build filename
    path = Path(output_path)
    if path.exists() and path.is_dir():
        fmt = str(output_format or "csv").lower().lstrip(".")
        ext = ".md" if fmt in {"md", "markdown"} else f".{fmt}"
        path = path / f"report{ext}"
    return write_report(path, output_format=output_format, **kwargs)


# Aliases
export_report = generate_report
generate_csv_report = lambda path, **kw: write_csv_report(path, **kw)  # noqa: E731
generate_json_report = lambda path, **kw: write_json_report(path, **kw)  # noqa: E731
generate_markdown_report = lambda path, **kw: write_markdown_report(path, **kw)  # noqa: E731


class ReportExporter:
    def __init__(self, title="", rows=None, columns=None, metadata=None, summary=None, report=None):
        self.report = _resolve_report(report, title=title, rows=rows, columns=columns, metadata=metadata, summary=summary)

    def export(self, path, output_format="csv"):
        return write_report(path, output_format=output_format, report=self.report)

    def export_csv(self, path):
        return write_csv_report(path, report=self.report)

    def export_json(self, path):
        return write_json_report(path, report=self.report)

    def export_markdown(self, path):
        return write_markdown_report(path, report=self.report)

    to_csv = export_csv
    to_json = export_json
    to_markdown = export_markdown


# aliases
ReportGenerator = ReportExporter
MultiFormatReporter = ReportExporter
ReportingEngine = ReportExporter
ReportWriter = ReportExporter
