"""Read-only Dataverse cloud-flow inventory and local XLSX reporting."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import httpx

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo

from .powerplatform_accounts import PowerPlatformApi
from .reporting import build_report_path, safe_excel_text


class PowerPlatformInventoryError(RuntimeError):
    """Raised when a safe Power Automate inventory cannot be produced."""


_TOKEN_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
)
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _read_path(item: Mapping[str, Any], path: str) -> Any:
    current: Any = item
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _as_safe_scalar(value: Any, *, limit: int = 500) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    text = str(value).replace("\x00", " ").strip()
    text = _TOKEN_PATTERN.sub("[REDACTED_TOKEN]", text)
    text = re.sub(r"[\r\n\t]+", " ", text)
    return text[:limit]


def _first_scalar(item: Mapping[str, Any], paths: tuple[str, ...], *, limit: int = 500) -> str:
    for path in paths:
        value = _read_path(item, path)
        if isinstance(value, Mapping):
            # Identity references can appear as nested objects. Extract only
            # display names or email addresses; never serialize raw objects.
            for nested_key in ("displayName", "name", "email", "userPrincipalName"):
                candidate = value.get(nested_key)
                if candidate is not None and not isinstance(candidate, (dict, list)):
                    result = _as_safe_scalar(candidate, limit=limit)
                    if result:
                        return result
        else:
            result = _as_safe_scalar(value, limit=limit)
            if result:
                return result
    return ""


def _extract_flow_rows(payload: Any) -> list[dict[str, Any]]:
    """Extract safe rows from Dataverse workflow metadata response shapes."""
    records: Any = None
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        for key in ("value", "cloudFlows", "flows", "items", "results", "data"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                records = candidate
                break
        if records is None and any(key in payload for key in ("id", "name", "workflowId", "displayName")):
            records = [payload]
        if records is None and payload.get("error"):
            error = payload.get("error")
            if isinstance(error, Mapping):
                message = error.get("message") or error.get("code") or "Power Platform returned an error."
            else:
                message = error
            raise PowerPlatformInventoryError(_as_safe_scalar(message, limit=700))
    if not isinstance(records, list):
        raise PowerPlatformInventoryError(
            "Dataverse returned an unrecognized cloud-flow metadata response. "
            "No raw response content was added to SKYFALL memory or chat."
        )

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in records:
        if not isinstance(raw, Mapping):
            continue
        properties = raw.get("properties") if isinstance(raw.get("properties"), Mapping) else {}
        merged: dict[str, Any] = dict(raw)
        merged["properties"] = properties
        flow_id = _first_scalar(
            merged,
            (
                "workflowId", "flowId", "properties.workflowId", "properties.flowId",
                "id", "name",
            ),
            limit=300,
        )
        display_name = _first_scalar(
            merged,
            (
                "displayName", "properties.displayName", "properties.name",
                "name", "properties.flowName", "flowName",
            ),
            limit=300,
        )
        if not display_name and flow_id:
            display_name = flow_id.rsplit("/", 1)[-1]
        if not flow_id:
            # Do not invent an identity for malformed rows.
            continue
        dedupe_key = flow_id.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        owner_name = _first_scalar(
            merged,
            (
                "owner.displayName", "owner.name", "properties.owner.displayName",
                "properties.owner.name", "properties.creator.displayName",
                "properties.creator.name",
            ),
            limit=200,
        )
        owner_email = _first_scalar(
            merged,
            (
                "owner.email", "owner.userPrincipalName", "properties.owner.email",
                "properties.owner.userPrincipalName", "properties.creator.email",
                "properties.creator.userPrincipalName",
            ),
            limit=200,
        )
        created_by = _first_scalar(
            merged,
            (
                "createdBy.displayName", "createdBy.name", "properties.createdBy.displayName",
                "properties.createdBy.name", "properties.creator.displayName",
            ),
            limit=200,
        )
        state = _first_scalar(
            merged,
            ("state", "properties.state", "status", "properties.status", "flowState"),
            limit=100,
        )
        flow_type = _first_scalar(
            merged,
            (
                "flowType", "properties.flowType", "category", "properties.category",
                "workflowCategory", "properties.workflowCategory", "typeLabel",
            ),
            limit=100,
        )
        created_on = _first_scalar(
            merged,
            ("createdTime", "createdOn", "properties.createdTime", "properties.createdOn", "systemData.createdAt"),
            limit=100,
        )
        modified_on = _first_scalar(
            merged,
            ("lastModifiedTime", "modifiedOn", "properties.lastModifiedTime", "properties.modifiedOn", "systemData.lastModifiedAt"),
            limit=100,
        )
        environment_name = _first_scalar(
            merged,
            ("environment.displayName", "properties.environment.displayName", "environmentName"),
            limit=200,
        )
        resource_id = _first_scalar(merged, ("id", "resourceId", "properties.resourceId"), limit=500)
        is_managed = _first_scalar(merged, ("isManaged", "properties.isManaged"), limit=30)

        normalized.append(
            {
                "flow_name": display_name or "Unnamed cloud flow",
                "flow_id": flow_id,
                "resource_id": resource_id,
                "status": state or "Not reported",
                "flow_type": flow_type or "Not reported",
                "owner_name": owner_name,
                "owner_email": owner_email if _EMAIL_PATTERN.match(owner_email) else "",
                "created_by": created_by,
                "created_on": created_on,
                "modified_on": modified_on,
                "environment_name": environment_name,
                "is_managed": is_managed,
            }
        )
    return sorted(normalized, key=lambda row: row["flow_name"].casefold())


def _status_bucket(value: str) -> str:
    state = (value or "").strip().casefold()
    if state in {"started", "enabled", "running", "on", "active"}:
        return "Enabled"
    if state in {"stopped", "disabled", "off", "suspended"}:
        return "Disabled / Suspended"
    return "Unknown / Other"


class PowerPlatformFlowInventory:
    """Inventory cloud flows in an explicitly selected environment."""

    def __init__(self, *, project_root: str | Path | None = None, api: PowerPlatformApi | None = None) -> None:
        self.project_root = Path(
            project_root or os.environ.get("SKYFALL_ROOT") or Path(__file__).resolve().parents[1]
        ).expanduser().resolve()
        self.api = api or PowerPlatformApi()
        self.accounts = self.api.store

    @staticmethod
    def _validate_environment_id(environment_id: str) -> str:
        value = (environment_id or "").strip()
        if not value:
            raise ValueError("Select a Power Platform environment before starting flow inventory.")
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError) as exc:
            raise ValueError(
                "Environment ID must be a valid GUID selected from SKYFALL's discovered Power Platform environments."
            ) from exc

    def inventory(
        self,
        *,
        environment_id: str,
        environment_name: str = "",
        environment_url: str = "",
        profile_id: str | None = None,
        generate_excel: bool = True,
    ) -> dict[str, Any]:
        if os.environ.get("SKYFALL_TEST_MODE") == "1":
            return {
                "success": False,
                "status": "blocked_test_mode",
                "error": "External Power Platform flow inventory is disabled in SKYFALL_TEST_MODE.",
                "cloud_resources_modified": False,
                "secrets_returned": False,
                "flow_definitions_read": False,
            }

        resolved_environment_id = self._validate_environment_id(environment_id)
        selected_profile_id = profile_id or self.accounts.get_active_profile_id()
        active_profile = self.accounts.get_profile(selected_profile_id) if selected_profile_id else None
        if not active_profile:
            return {
                "success": False,
                "status": "not_authenticated",
                "error": "No saved Microsoft account is selected. Add or select a Power Platform account first.",
                "cloud_resources_modified": False,
                "secrets_returned": False,
                "flow_definitions_read": False,
            }
        if not environment_url:
            discovered = self.api.list_environments(selected_profile_id)
            match = next(
                (item for item in discovered.get("environments", []) if str(item.get("environment_id")) == resolved_environment_id),
                None,
            )
            if match:
                environment_url = str(match.get("environment_url") or "")
                environment_name = environment_name or str(match.get("name") or "")
        try:
            raw_rows = self.api.list_flows(selected_profile_id, environment_url)
            flows = _extract_flow_rows({"value": raw_rows})
        except (ValueError, RuntimeError, httpx.HTTPError) as exc:
            raise PowerPlatformInventoryError(str(exc)) from exc

        for flow in flows:
            if not flow.get("environment_name"):
                flow["environment_name"] = (environment_name or "").strip()

        status_counts = Counter(_status_bucket(item.get("status", "")) for item in flows)
        type_counts = Counter(item.get("flow_type") or "Not reported" for item in flows)
        owners = sorted(
            {item.get("owner_name") or item.get("owner_email") for item in flows if item.get("owner_name") or item.get("owner_email")},
            key=str.casefold,
        )

        report_path: str | None = None
        worksheets: list[str] = []
        if generate_excel:
            report_path, worksheets = self._write_excel_report(
                flows=flows,
                environment_id=resolved_environment_id,
                environment_name=(environment_name or "").strip() or "Selected Environment",
                active_profile=active_profile,
            )

        return {
            "success": True,
            "status": "success",
            "operation": "power_automate_flow_inventory",
            "environment": {
                "name": (environment_name or "").strip() or "Selected Environment",
                "environment_id": resolved_environment_id,
            },
            "active_profile": {
                "label": _as_safe_scalar(active_profile.get("name") or "Microsoft account", limit=120),
                "user": _as_safe_scalar(active_profile.get("username") or "", limit=160),
                "profile_id": active_profile.get("profile_id"),
            },
            "flow_count": len(flows),
            "enabled_count": status_counts.get("Enabled", 0),
            "disabled_or_suspended_count": status_counts.get("Disabled / Suspended", 0),
            "unknown_status_count": status_counts.get("Unknown / Other", 0),
            "flow_types": dict(sorted(type_counts.items(), key=lambda pair: pair[0].casefold())),
            "owner_count": len(owners),
            "report": {
                "format": "xlsx" if generate_excel else None,
                "path": report_path,
                "file_name": Path(report_path).name if report_path else None,
                "worksheets": worksheets,
            } if generate_excel else None,
            "preview": [
                {
                    "name": item["flow_name"],
                    "status": item["status"],
                    "type": item["flow_type"],
                    "owner": item.get("owner_name") or item.get("owner_email") or "Not reported",
                    "modified_on": item["modified_on"],
                }
                for item in flows[:10]
            ],
            "data_source": "Microsoft Dataverse Web API (workflow table; metadata columns only)",
            "coverage": "Solution cloud flows visible to the selected Microsoft account in the explicitly selected Dataverse environment. My Flows is not supported by Microsoft's documented code path.",
            "flow_definitions_read": False,
            "connection_details_read": False,
            "secrets_returned": False,
            "cloud_resources_modified": False,
            "note": "SKYFALL requests allow-listed workflow metadata columns only. Flow definitions, action payloads, connection details, credentials and secrets are not read or included.",
        }

    def _write_excel_report(
        self,
        *,
        flows: list[dict[str, Any]],
        environment_id: str,
        environment_name: str,
        active_profile: Mapping[str, Any],
    ) -> tuple[str, list[str]]:
        report_dir = self.project_root / "reports" / "PowerPlatform"
        output_path = build_report_path(
            report_dir,
            ["Power-Automate-Flows", environment_name],
        )
        temp_path = output_path.with_name(output_path.stem + ".tmp.xlsx")

        workbook = Workbook()
        overview = workbook.active
        overview.title = "Overview"
        status_counts = Counter(_status_bucket(item.get("status", "")) for item in flows)
        type_counts = Counter(item.get("flow_type") or "Not reported" for item in flows)
        generated_local = datetime.now().astimezone()
        overview.append(["SKYFALL — Power Automate Cloud Flow Inventory"])
        overview.append(["Generated (local)", generated_local.isoformat(timespec="seconds")])
        overview.append(["Environment", environment_name])
        overview.append(["Environment ID", environment_id])
        overview.append(["Microsoft account profile", _as_safe_scalar(active_profile.get("name") or "Selected account", limit=160)])
        overview.append(["Signed-in user", _as_safe_scalar(active_profile.get("username") or "Not supplied", limit=160)])
        overview.append(["Total cloud flows discovered", len(flows)])
        overview.append(["Enabled flows", status_counts.get("Enabled", 0)])
        overview.append(["Disabled / suspended flows", status_counts.get("Disabled / Suspended", 0)])
        overview.append(["Unknown / other status", status_counts.get("Unknown / Other", 0)])
        overview.append(["Distinct owners reported", len({item.get('owner_name') or item.get('owner_email') for item in flows if item.get('owner_name') or item.get('owner_email')})])
        overview.append(["Cloud changes performed", "No — read-only inventory"])
        overview.append(["Flow definitions / action payloads read", "No"])
        overview.append(["Connection details / secrets read", "No"])
        overview.append(["Data source", "Dataverse Web API: workflow metadata columns only"])
        overview.append(["Coverage", "Cloud flows visible to the selected Microsoft account in the selected environment; permissions determine coverage."])
        overview.append([])
        overview.append(["Flows by status", "Count"])
        for label, count in sorted(status_counts.items(), key=lambda pair: pair[0].casefold()):
            overview.append([label, count])
        overview.append([])
        overview.append(["Flows by type", "Count"])
        for label, count in sorted(type_counts.items(), key=lambda pair: pair[0].casefold()):
            overview.append([label, count])

        flow_columns = [
            ("Flow name", "flow_name"),
            ("Flow ID", "flow_id"),
            ("Status", "status"),
            ("Flow type", "flow_type"),
            ("Owner", "owner_name"),
            ("Owner email", "owner_email"),
            ("Created by", "created_by"),
            ("Created on", "created_on"),
            ("Last modified", "modified_on"),
            ("Environment", "environment_name"),
            ("Environment ID", "_environment_id"),
            ("Managed", "is_managed"),
            ("Resource ID", "resource_id"),
        ]
        flow_rows = [dict(item, _environment_id=environment_id) for item in flows]
        self._append_table(workbook.create_sheet("Cloud Flows"), flow_columns, flow_rows, "CloudFlowsTable")

        status_sheet = workbook.create_sheet("Status Summary")
        self._append_table(
            status_sheet,
            [("Status group", "label"), ("Flow count", "count")],
            [{"label": label, "count": count} for label, count in sorted(status_counts.items(), key=lambda pair: pair[0].casefold())],
            "FlowStatusTable",
        )

        type_sheet = workbook.create_sheet("Flow Types")
        self._append_table(
            type_sheet,
            [("Flow type", "label"), ("Flow count", "count")],
            [{"label": label, "count": count} for label, count in sorted(type_counts.items(), key=lambda pair: pair[0].casefold())],
            "FlowTypesTable",
        )

        owner_counts = Counter(
            item.get("owner_name") or item.get("owner_email")
            for item in flows
            if item.get("owner_name") or item.get("owner_email")
        )
        owner_sheet = workbook.create_sheet("Owners")
        self._append_table(
            owner_sheet,
            [("Owner", "owner"), ("Flow count", "count")],
            [{"owner": owner, "count": count} for owner, count in sorted(owner_counts.items(), key=lambda pair: str(pair[0]).casefold())],
            "FlowOwnersTable",
        )

        notes_sheet = workbook.create_sheet("Discovery Notes")
        self._append_table(
            notes_sheet,
            [("Topic", "topic"), ("Details", "details")],
            [
                {"topic": "Environment", "details": f"{environment_name} ({environment_id})"},
                {"topic": "Microsoft account profile", "details": _as_safe_scalar(active_profile.get("name") or "Selected account", limit=160)},
                {"topic": "Inventory scope", "details": "Solution cloud flows visible to the selected Microsoft account in the explicitly selected environment. My Flows is not supported by Microsoft's documented code path."},
                {"topic": "Permissions", "details": "The signed-in user's permissions determine which flow records can be listed."},
                {"topic": "Privacy", "details": "Flow definitions, action payloads, connection details, credentials and secrets are not read or exported."},
                {"topic": "Changes", "details": "No cloud resources were created, changed or deleted."},
            ],
            "FlowDiscoveryNotesTable",
        )

        self._sanitize_workbook_text_cells(workbook)
        self._format_workbook(workbook)
        try:
            workbook.save(temp_path)
            os.replace(temp_path, output_path)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
        return str(output_path), [sheet.title for sheet in workbook.worksheets]

    @staticmethod
    def _append_table(worksheet: Any, columns: list[tuple[str, str]], rows: list[dict[str, Any]], table_name: str) -> None:
        worksheet.append([label for label, _key in columns])
        for record in rows:
            values = []
            for _label, key in columns:
                value = record.get(key, "")
                if value is None:
                    value = ""
                values.append(safe_excel_text(value))
            worksheet.append(values)
        if rows:
            end_column = worksheet.cell(row=1, column=len(columns)).column_letter
            table = Table(displayName=table_name, ref=f"A1:{end_column}{len(rows) + 1}")
            table.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False,
                showRowStripes=True, showColumnStripes=False,
            )
            worksheet.add_table(table)

    @staticmethod
    def _sanitize_workbook_text_cells(workbook: Workbook) -> None:
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    cell.value = safe_excel_text(cell.value)

    @staticmethod
    def _format_workbook(workbook: Workbook) -> None:
        for sheet in workbook.worksheets:
            sheet.sheet_view.showGridLines = False
            sheet.freeze_panes = "A2"
            for cell in sheet[1]:
                cell.font = Font(name="Aptos Display", bold=True, color="FFFFFF", size=12)
                cell.fill = PatternFill("solid", fgColor="183A63")
                cell.alignment = Alignment(vertical="center", wrap_text=True)
            sheet.row_dimensions[1].height = 28
            for column_cells in sheet.columns:
                letter = column_cells[0].column_letter
                width = 12
                for cell in column_cells[:300]:
                    width = max(width, min(len(str(cell.value or "")) + 2, 48))
                sheet.column_dimensions[letter].width = min(width, 48)
