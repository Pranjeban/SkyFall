"""Validated metadata registry for SKYFALL's explicitly enabled capabilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    tool_name: str
    category: str
    description: str
    risk: str
    status: str
    requires_approval: bool
    execution_enabled: bool
    input_schema: dict[str, Any]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tool_name": self.tool_name,
            "category": self.category,
            "description": self.description,
            "risk": self.risk,
            "status": self.status,
            "requires_approval": self.requires_approval,
            "execution_enabled": self.execution_enabled,
            "input_schema": self.input_schema,
            "limitations": list(self.limitations),
        }


class CapabilityRegistry:
    """Loads capability metadata; metadata alone never makes arbitrary code executable."""

    def __init__(self, catalogue_path: str | Path) -> None:
        self.catalogue_path = Path(catalogue_path).expanduser().resolve()
        if not self.catalogue_path.is_file():
            raise FileNotFoundError(f"Capability catalogue not found: {self.catalogue_path}")

        raw = json.loads(self.catalogue_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("Unsupported or invalid capability catalogue schema.")

        server = raw.get("server")
        entries = raw.get("capabilities")
        if not isinstance(server, dict) or not isinstance(entries, list):
            raise ValueError("Capability catalogue must contain server metadata and a capabilities array.")
        self.server = server
        self._capabilities: dict[str, Capability] = {}
        tool_names: set[str] = set()

        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Every capability entry must be an object.")
            required = ("id", "name", "tool_name", "category", "description", "risk", "status")
            missing = [key for key in required if not entry.get(key)]
            if missing:
                raise ValueError(f"Capability entry is missing required fields: {', '.join(missing)}")
            capability_id = str(entry["id"])
            tool_name = str(entry["tool_name"])
            if capability_id in self._capabilities:
                raise ValueError(f"Duplicate capability ID: {capability_id}")
            if tool_name in tool_names:
                raise ValueError(f"Duplicate MCP tool name: {tool_name}")
            tool_names.add(tool_name)
            schema = entry.get("input_schema", {"type": "object", "properties": {}, "required": []})
            if not isinstance(schema, dict) or schema.get("type") != "object":
                raise ValueError(f"Invalid input schema for capability: {capability_id}")
            self._capabilities[capability_id] = Capability(
                id=capability_id,
                name=str(entry["name"]),
                tool_name=tool_name,
                category=str(entry["category"]),
                description=str(entry["description"]),
                risk=str(entry.get("risk", "unknown")),
                status=str(entry.get("status", "disabled")),
                requires_approval=bool(entry.get("requires_approval", True)),
                execution_enabled=bool(entry.get("execution_enabled", False)),
                input_schema=schema,
                limitations=tuple(str(x) for x in entry.get("limitations", [])),
            )

    @classmethod
    def default(cls) -> "CapabilityRegistry":
        project_root = Path(__file__).resolve().parents[1]
        return cls(project_root / "configuration" / "capabilities.json")

    def list(self, category: str = "all", enabled_only: bool = True) -> list[Capability]:
        clean_category = (category or "all").strip().lower()
        if clean_category not in {"all", "*"}:
            result = [c for c in self._capabilities.values() if c.category.lower() == clean_category]
        else:
            result = list(self._capabilities.values())
        if enabled_only:
            result = [c for c in result if c.status == "enabled" and c.execution_enabled]
        return sorted(result, key=lambda c: (c.category, c.name.lower()))

    def get(self, capability_id: str) -> Capability:
        clean_id = (capability_id or "").strip()
        try:
            return self._capabilities[clean_id]
        except KeyError as exc:
            raise KeyError(f"Unknown SKYFALL capability: {clean_id}") from exc

    def find_by_tool_name(self, tool_name: str) -> Capability | None:
        """Return the enabled capability registered for an exact MCP tool name."""
        clean_name = (tool_name or "").strip()
        if not clean_name:
            return None
        for capability in self._capabilities.values():
            if (
                capability.tool_name == clean_name
                and capability.status == "enabled"
                and capability.execution_enabled
            ):
                return capability
        return None

    def find_by_operation(self, operation: str) -> Capability | None:
        """Return the enabled capability matching an exact operation identifier.

        Operation lookup accepts either an exact capability ID or an exact MCP
        tool name. Disabled capabilities are never returned.
        """
        clean_operation = (operation or "").strip()
        if not clean_operation:
            return None
        capability = self._capabilities.get(clean_operation)
        if (
            capability is not None
            and capability.status == "enabled"
            and capability.execution_enabled
        ):
            return capability
        return self.find_by_tool_name(clean_operation)

    def is_tool_enabled(self, tool_name: str) -> bool:
        return any(
            c.tool_name == tool_name and c.status == "enabled" and c.execution_enabled
            for c in self._capabilities.values()
        )
