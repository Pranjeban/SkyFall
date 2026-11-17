"""Read-only MCP tools for explicitly approved SKYFALL workspace metadata."""

from __future__ import annotations

import json
from typing import Any

from skyfall_workspace.manager import WorkspaceManager


def _manager() -> WorkspaceManager:
    return WorkspaceManager()


def get_workspace_index_status() -> str:
    """Return aggregate status for workspaces whose metadata the user shared with Copilot."""
    return json.dumps(_manager().get_ai_index_status(), ensure_ascii=False, indent=2)


def list_workspaces() -> str:
    """List only enabled workspaces for which the user explicitly enabled AI metadata sharing."""
    items = _manager().list_for_ai()
    # A workspace path is included only after the user has explicitly enabled
    # metadata sharing for that root in the local SKYFALL UI. Internal scan-error
    # strings are deliberately omitted from the model-facing response.
    allowed_fields = {
        "id", "path", "display_name", "enabled", "allow_ai_metadata",
        "added_at", "last_scan_at", "scan_status", "file_count", "skipped_count",
    }
    safe_items = [
        {key: value for key, value in item.items() if key in allowed_fields}
        for item in items
    ]
    return json.dumps({
        "count": len(safe_items),
        "workspaces": safe_items,
        "source_contents_shared": False,
        "scope": "explicitly_consented_workspaces_only",
    }, ensure_ascii=False, indent=2)


def search_workspace_files(
    query: str,
    file_type: str = "all",
    workspace_id: str = "",
    limit: int = 20,
) -> str:
    """Search filenames and extracted metadata in explicitly shared workspaces; never returns source code."""
    results = _manager().search_for_ai(
        query=query,
        file_type=file_type,
        workspace_id=workspace_id or None,
        limit=limit,
    )
    safe_results: list[dict[str, Any]] = []
    for item in results:
        safe_results.append({key: value for key, value in item.items() if key not in {"sensitive_flag", "sha256"}})
    return json.dumps({
        "query": query,
        "count": len(safe_results),
        "results": safe_results,
        "source_contents_shared": False,
    }, ensure_ascii=False, indent=2)


def describe_workspace_file(file_id: str) -> str:
    """Describe an indexed file using static metadata from an explicitly shared workspace; source code is not returned."""
    result = _manager().describe_file_for_ai(file_id)
    result.pop("sensitive_flag", None)
    result.pop("sha256", None)
    return json.dumps({
        "file": result,
        "source_contents_shared": False,
        "analysis_method": "local_static_analysis_only",
    }, ensure_ascii=False, indent=2)
