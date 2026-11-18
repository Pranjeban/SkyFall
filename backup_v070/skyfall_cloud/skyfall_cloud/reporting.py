"""Shared helpers for safe, human-readable SKYFALL report files."""

from __future__ import annotations

import re
from datetime import datetime
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
