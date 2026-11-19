"""MCP tool wrappers for multi-format SKYFALL reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skyfall_cloud.reporting import (
    generate_report as _generate_report,
    prepare_report as _prepare_report,
    write_csv_report as _write_csv_report,
    write_json_report as _write_json_report,
    write_markdown_report as _write_markdown_report,
)


def _loads(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def generate_csv_report(
    output_path: str,
    title: str = "SKYFALL Report",
    rows: Any = None,
    columns: Any = None,
    metadata: Any = None,
) -> str:
    path = _write_csv_report(
        output_path,
        title=title,
        rows=_loads(rows) if rows is not None else None,
        columns=_loads(columns) if columns is not None else None,
        metadata=_loads(metadata) if metadata is not None else None,
    )
    return json.dumps({"format": "csv", "path": str(path)}, ensure_ascii=False, indent=2)


def generate_json_report(
    output_path: str,
    title: str = "SKYFALL Report",
    rows: Any = None,
    columns: Any = None,
    metadata: Any = None,
) -> str:
    path = _write_json_report(
        output_path,
        title=title,
        rows=_loads(rows) if rows is not None else None,
        columns=_loads(columns) if columns is not None else None,
        metadata=_loads(metadata) if metadata is not None else None,
    )
    return json.dumps({"format": "json", "path": str(path)}, ensure_ascii=False, indent=2)


def generate_markdown_report(
    output_path: str,
    title: str = "SKYFALL Report",
    rows: Any = None,
    columns: Any = None,
    metadata: Any = None,
) -> str:
    path = _write_markdown_report(
        output_path,
        title=title,
        rows=_loads(rows) if rows is not None else None,
        columns=_loads(columns) if columns is not None else None,
        metadata=_loads(metadata) if metadata is not None else None,
    )
    return json.dumps({"format": "markdown", "path": str(path)}, ensure_ascii=False, indent=2)


def generate_report(
    output_path: str,
    output_format: str = "csv",
    title: str = "SKYFALL Report",
    rows: Any = None,
    columns: Any = None,
    metadata: Any = None,
) -> str:
    path = _generate_report(
        output_path,
        output_format=output_format,
        title=title,
        rows=_loads(rows) if rows is not None else None,
        columns=_loads(columns) if columns is not None else None,
        metadata=_loads(metadata) if metadata is not None else None,
    )
    return json.dumps({"format": output_format, "path": str(path)}, ensure_ascii=False, indent=2)
