"""Cross-platform intelligence for Azure and Power Platform inventories (v1.1 Module 5).

Pure, offline data correlation: no HTTP client, identity authority or tenant
access is used. Inputs are caller-supplied inventory records; malformed or
non-dict rows are skipped, results are deterministically ordered, and fields
resembling credentials are never copied into returned data.
"""

from __future__ import annotations

from typing import Any

_SECRET_FRAGMENTS = ("token", "secret", "password", "credential", "connectionstring", "key")
_FIELD_MAP = {
    "id": "id",
    "resource_id": "id",
    "resourceId": "id",
    "environment_id": "environment_id",
    "environmentId": "environment_id",
    "name": "name",
    "displayName": "name",
    "display_name": "name",
    "type": "type",
    "resourceType": "type",
    "resource_group": "resource_group",
    "resourceGroup": "resource_group",
    "location": "location",
    "region": "region",
    "state": "state",
    "kind": "kind",
    "url": "url",
    "category": "category",
}
_MAX_TEXT = 512


class CrossPlatformIntelligenceError(RuntimeError):
    """User-facing correlation failure that never contains credential material."""


class CrossPlatformIntelligence:
    """Correlate Azure resources with Power Platform inventory records."""

    @staticmethod
    def _rows(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, (list, tuple)):
            return [row for row in value if isinstance(row, dict)]
        return []

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()[:_MAX_TEXT]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)[:_MAX_TEXT]
        return ""

    @staticmethod
    def _norm(value: str) -> str:
        chars = [ch if ch.isalnum() else "-" for ch in value.lower()]
        return "-".join("".join(chars).split("-")).strip("-")

    @classmethod
    def _clean(cls, item: dict[str, Any], source: str) -> dict[str, Any]:
        record: dict[str, Any] = {"source": source}
        for key, target in _FIELD_MAP.items():
            if any(fragment in key.lower() for fragment in _SECRET_FRAGMENTS):
                continue
            value = cls._text(item.get(key))
            if value and not record.get(target):
                record[target] = (
                    value.strip("{}") if target in ("id", "environment_id") else value
                )
        return record

    @classmethod
    def _tags(cls, item: dict[str, Any]) -> list[str]:
        tags = item.get("tags")
        if isinstance(tags, dict):
            values = [cls._text(v) for v in tags.values()]
        elif isinstance(tags, (list, tuple)):
            values = [cls._text(v) for v in tags]
        elif isinstance(tags, str):
            values = [tags]
        else:
            values = []
        return [cls._norm(value) for value in values if value]

    @classmethod
    def _keys(cls, item: dict[str, Any]) -> list[str]:
        keys: list[str] = []
        for field in (
            "name", "displayName", "display_name", "id", "resource_id",
            "resourceId", "environment_id", "environmentId",
        ):
            value = cls._norm(cls._text(item.get(field)).strip("{}"))
            if value and value not in keys:
                keys.append(value)
        for tag in cls._tags(item):
            if tag not in keys:
                keys.append(tag)
        return keys

    @classmethod
    def _match_reason(cls, left: dict[str, Any], right: dict[str, Any]) -> str | None:
        """Best-effort match by normalized name/ID first, then by tag value."""
        name_fields = ("name", "displayName", "display_name")
        id_fields = ("id", "resource_id", "resourceId", "environment_id", "environmentId")
        for fields, reason in ((name_fields, "name"), (id_fields, "identifier")):
            for field in fields:
                value = cls._norm(cls._text(left.get(field)).strip("{}"))
                if value and any(
                    value == cls._norm(cls._text(right.get(other)).strip("{}"))
                    for other in fields
                ):
                    return reason
        if any(tag in cls._tags(right) for tag in cls._tags(left)):
            return "tag"
        return None

    @classmethod
    def _resolve(
        cls, rows: list[dict[str, Any]], source: str, value: Any
    ) -> dict[str, Any] | None:
        wanted = cls._norm(cls._text(value).strip("{}"))
        if not wanted:
            return None
        for row in rows:
            if wanted in cls._keys(row):
                return cls._clean(row, source)
        return None

    def unified_inventory(
        self,
        azure_resources: Any,
        pp_environments: Any,
        pp_apps: Any = (),
        pp_flows: Any = (),
    ) -> dict[str, Any]:
        """Return per-platform counts plus a flat, source-tagged item list."""
        groups = (
            ("azure", "azure", azure_resources),
            ("pp_environment", "pp_environments", pp_environments),
            ("pp_app", "pp_apps", pp_apps),
            ("pp_flow", "pp_flows", pp_flows),
        )
        items: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for source, count_key, rows in groups:
            cleaned = [self._clean(row, source) for row in self._rows(rows)]
            items.extend(cleaned)
            counts[count_key] = len(cleaned)
        return {"success": True, "counts": counts, "count": len(items), "items": items}

    def map_dependencies(
        self,
        azure_resources: Any,
        pp_environments: Any,
        pp_connections: Any = (),
    ) -> dict[str, Any]:
        """Build deterministic best-effort dependency edges.

        Heuristic: connection records are resolved by normalized source/target
        names or IDs; remaining edges come from a shared normalized name/ID or
        shared tag value between an Azure resource and a Power Platform
        environment. Only stable matches produce edges; no network lookup or
        identity resolution is attempted, and ambiguous or missing references
        are skipped.
        """
        azure = self._rows(azure_resources)
        pp = self._rows(pp_environments)
        edges: list[dict[str, Any]] = []
        signatures: list[tuple[Any, ...]] = []

        def add(left: dict[str, Any] | None, right: dict[str, Any] | None, reason: str) -> None:
            if left is None or right is None:
                return
            signature = (
                left.get("source"), left.get("id") or left.get("name", ""),
                right.get("source"), right.get("id") or right.get("name", ""),
                reason,
            )
            if signature in signatures:
                return
            signatures.append(signature)
            edges.append({
                "source": left.get("name") or left.get("id", ""),
                "target": right.get("name") or right.get("id", ""),
                "source_platform": left["source"],
                "target_platform": right["source"],
                "match": reason,
            })

        for connection in self._rows(pp_connections):
            for from_field in ("source", "from", "sourceName", "fromEnvironment"):
                origin = self._resolve(azure, "azure", connection.get(from_field))
                if origin is None:
                    origin = self._resolve(pp, "pp_environment", connection.get(from_field))
                if origin is None:
                    continue
                for to_field in ("target", "to", "targetName", "toEnvironment"):
                    destination = self._resolve(pp, "pp_environment", connection.get(to_field))
                    if destination is None:
                        destination = self._resolve(azure, "azure", connection.get(to_field))
                    add(origin, destination, "connection")
                break

        for azure_row in azure:
            for pp_row in pp:
                reason = self._match_reason(azure_row, pp_row)
                if reason:
                    add(
                        self._clean(azure_row, "azure"),
                        self._clean(pp_row, "pp_environment"),
                        reason,
                    )
        return {
            "success": True,
            "method": "name_id_tag_heuristic",
            "edges": edges,
            "count": len(edges),
        }

    def find_coverage_gaps(
        self, azure_resources: Any, pp_environments: Any
    ) -> dict[str, Any]:
        """Return records with no counterpart on the other platform."""
        azure = self._rows(azure_resources)
        pp = self._rows(pp_environments)
        azure_only = [
            self._clean(row, "azure")
            for row in azure
            if not any(self._match_reason(row, other) for other in pp)
        ]
        pp_only = [
            self._clean(row, "pp_environment")
            for row in pp
            if not any(self._match_reason(row, other) for other in azure)
        ]
        return {
            "success": True,
            "azure_only": azure_only,
            "pp_only": pp_only,
            "counts": {"azure_only": len(azure_only), "pp_only": len(pp_only)},
            "count": len(azure_only) + len(pp_only),
        }

    def compare_postures(
        self, azure_items: Any, pp_items: Any, key: str = "name"
    ) -> dict[str, Any]:
        """Compare two inventories by an allowlisted, non-secret scalar key."""
        field = self._text(key) or "name"
        if any(fragment in field.lower() for fragment in _SECRET_FRAGMENTS):
            field = "name"

        aliases = ("name", "displayName", "display_name") if field == "name" else (field,)

        def values(rows: Any) -> list[str]:
            result: list[str] = []
            for row in self._rows(rows):
                value = ""
                for alias in aliases:
                    value = self._text(row.get(alias))
                    if value:
                        break
                if value and value not in result:
                    result.append(value)
            return result

        azure_values, pp_values = values(azure_items), values(pp_items)
        common = [value for value in azure_values if value in pp_values]
        only_azure = [value for value in azure_values if value not in pp_values]
        only_pp = [value for value in pp_values if value not in azure_values]
        return {
            "success": True,
            "key": field,
            "common": common,
            "only_azure": only_azure,
            "only_pp": only_pp,
            "counts": {
                "common": len(common),
                "only_azure": len(only_azure),
                "only_pp": len(only_pp),
            },
        }

    def summarize(
        self,
        azure_resources: Any,
        pp_environments: Any,
        pp_apps: Any = (),
        pp_flows: Any = (),
    ) -> dict[str, Any]:
        """Digest inventory counts and the first five coverage gaps."""
        inventory = self.unified_inventory(
            azure_resources, pp_environments, pp_apps, pp_flows
        )
        gaps = self.find_coverage_gaps(azure_resources, pp_environments)
        top_gaps: list[dict[str, str]] = []
        for platform, entries in (
            ("azure", gaps["azure_only"]), ("pp", gaps["pp_only"])
        ):
            for entry in entries:
                if len(top_gaps) >= 5:
                    break
                top_gaps.append({
                    "platform": platform,
                    "name": entry.get("name") or entry.get("id", ""),
                })
        counts = dict(inventory["counts"])
        counts["coverage_gaps"] = gaps["count"]
        return {
            "success": True,
            "counts": counts,
            "total_items": inventory["count"],
            "coverage_gap_count": gaps["count"],
            "top_gaps": top_gaps,
        }
