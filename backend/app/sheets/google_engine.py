"""Google Sheets/Drive implementation of the V1 sheet engine contract."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import re
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

from ..core.settings import Settings
from ..workbook.inspection import WorkbookInspection
from .engine import SheetsEngine

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
SCOPES = [SHEETS_SCOPE, DRIVE_SCOPE]
_A1_CELL_RE = re.compile(r"^\$?([A-Za-z]{1,4})\$?([0-9]{1,7})$")
_A1_COL_RE = re.compile(r"^\$?([A-Za-z]{1,4})$")
_A1_ROW_RE = re.compile(r"^\$?([0-9]{1,7})$")

DEFAULT_OUTPUT_RANGES: tuple[str, ...] = (
    "out_value_ps_pess",
    "out_value_ps_base",
    "out_value_ps_opt",
    "out_value_ps_weighted",
    "out_equity_value_weighted",
    "out_enterprise_value_weighted",
    "OUT_WACC",
    "out_terminal_g",
)

_NAMED_RANGE_ALIASES: dict[str, tuple[str, ...]] = {}
_INDEX_PREFILLED_APPEND_TABLES: frozenset[str] = frozenset(
    {"log_actions_table", "log_assumptions_table", "log_story_table"}
)


@dataclass(frozen=True)
class _RangeBounds:
    sheet: str
    row_start: int | None
    row_end: int | None
    col_start: int | None
    col_end: int | None


@dataclass(frozen=True)
class _SpreadsheetSchema:
    sheet_titles: frozenset[str]
    named_ranges: frozenset[str]
    named_range_bounds: dict[str, _RangeBounds]
    formula_owned_bounds: tuple[_RangeBounds, ...]


@dataclass
class GoogleSheetsEngine(SheetsEngine):
    """Google OAuth-backed Sheets compute engine for valuation workflows."""

    settings: Settings
    output_ranges: tuple[str, ...] = DEFAULT_OUTPUT_RANGES
    logbook_sheet_name: str = "Runs"
    _credentials: Any = field(default=None, init=False, repr=False)
    _sheets: Any = field(default=None, init=False, repr=False)
    _drive: Any = field(default=None, init=False, repr=False)
    _template_file_id: str | None = field(default=None, init=False, repr=False)
    _logbook_file_id: str | None = field(default=None, init=False, repr=False)
    _named_ranges_cache: dict[str, set[str]] = field(default_factory=dict, init=False, repr=False)
    _schema_cache: dict[str, _SpreadsheetSchema] = field(default_factory=dict, init=False, repr=False)
    _logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("finance_research_agent.sheets.google"),
        init=False,
        repr=False,
    )

    def copy_template(self, run_id: str, ticker: str) -> str:
        drive = self._drive_service()
        template_file_id = self._resolve_template_file_id(drive)
        template_name = self.settings.sheets_template_file
        new_name = f"{ticker.strip().upper()}_{run_id}_{template_name}"
        self._logger.info(
            "copy_template_start run_id=%s ticker=%s template_file_id=%s new_name=%s",
            run_id,
            ticker.strip().upper(),
            template_file_id,
            new_name,
        )
        copied = (
            drive.files()
            .copy(
                fileId=template_file_id,
                body={"name": new_name},
                fields="id,mimeType",
                supportsAllDrives=True,
            )
            .execute()
        )
        spreadsheet_id = copied.get("id")
        if not spreadsheet_id:
            raise RuntimeError("Template copy succeeded but spreadsheet ID was missing.")
        mime_type = copied.get("mimeType")
        if mime_type != "application/vnd.google-apps.spreadsheet":
            raise RuntimeError(
                "Template copy is not a Google Spreadsheet. Open/import the template "
                "into Google Sheets before run execution."
            )
        self._logger.info(
            "copy_template_end run_id=%s spreadsheet_id=%s mime_type=%s",
            run_id,
            spreadsheet_id,
            mime_type,
        )
        return str(spreadsheet_id)

    def write_named_ranges(self, spreadsheet_id: str, values: dict[str, object]) -> None:
        if not values:
            return
        valid_values = self._validate_named_range_write_targets(
            spreadsheet_id=spreadsheet_id,
            values=values,
        )
        normalized_values = self._coerce_named_range_write_shapes(
            spreadsheet_id=spreadsheet_id,
            values=valid_values,
        )
        self._logger.info(
            "write_named_ranges spreadsheet_id=%s count=%s ranges=%s",
            spreadsheet_id,
            len(normalized_values),
            ",".join(sorted(normalized_values.keys())[:20]),
        )
        data = [
            {"range": key, "values": matrix}
            for key, matrix in normalized_values.items()
        ]
        (
            self._sheets_service()
            .spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": data},
            )
            .execute()
        )

    def read_outputs(self, spreadsheet_id: str) -> dict[str, object]:
        self._logger.info(
            "read_outputs spreadsheet_id=%s count=%s",
            spreadsheet_id,
            len(self.output_ranges),
        )
        response = self.read_named_ranges(
            spreadsheet_id=spreadsheet_id,
            names=list(self.output_ranges),
            value_render_option="UNFORMATTED_VALUE",
        )
        results: dict[str, object] = {}
        for range_name in self.output_ranges:
            rows = response.get(range_name, [])
            results[range_name] = rows[0][0] if rows and rows[0] else None
        self._logger.info(
            "read_outputs_done spreadsheet_id=%s keys=%s",
            spreadsheet_id,
            ",".join(sorted(results.keys())),
        )
        return results

    def read_named_ranges(
        self,
        spreadsheet_id: str,
        names: list[str],
        *,
        value_render_option: str = "UNFORMATTED_VALUE",
    ) -> dict[str, list[list[object]]]:
        if not names:
            return {}
        normalized = _normalize_named_range_list(names)
        known_ranges = self._load_named_ranges(spreadsheet_id)
        resolved_targets, missing = _resolve_named_range_targets(
            names=normalized,
            known_ranges=known_ranges,
        )
        if missing:
            raise ValueError(
                "Unknown named ranges for read_named_ranges: "
                f"{', '.join(sorted(missing)[:10])}"
            )
        self._logger.info(
            "read_named_ranges spreadsheet_id=%s count=%s ranges=%s render=%s",
            spreadsheet_id,
            len(normalized),
            ",".join([resolved_targets[name] for name in normalized[:20]]),
            value_render_option,
        )
        response = (
            self._sheets_service()
            .spreadsheets()
            .values()
            .batchGet(
                spreadsheetId=spreadsheet_id,
                ranges=[resolved_targets[name] for name in normalized],
                valueRenderOption=value_render_option,
            )
            .execute()
        )
        output: dict[str, list[list[object]]] = {}
        for requested, value_range in zip(normalized, response.get("valueRanges", [])):
            values = value_range.get("values", [])
            if isinstance(values, list):
                output[requested] = values
            else:
                output[requested] = []
        self._logger.info(
            "read_named_ranges_done spreadsheet_id=%s resolved=%s",
            spreadsheet_id,
            len(output),
        )
        return output

    def append_named_table_rows(
        self,
        spreadsheet_id: str,
        table_name: str,
        rows: list[list[object]],
    ) -> None:
        if not rows:
            return
        bounds = self._resolve_named_table_bounds(
            spreadsheet_id=spreadsheet_id,
            table_name=table_name,
        )
        width, height = _bounds_size(bounds)
        if width <= 0 or height <= 0:
            raise ValueError(
                f"Named table range has invalid dimensions: {table_name}"
            )
        normalized_rows = _normalize_rows_for_table(rows, width=width)

        table_a1 = _bounds_to_a1_range(bounds)
        table_values = (
            self._sheets_service()
            .spreadsheets()
            .values()
            .get(
                spreadsheetId=spreadsheet_id,
                range=table_a1,
                valueRenderOption="UNFORMATTED_VALUE",
            )
            .execute()
            .get("values", [])
        )
        next_row_offset = _first_empty_row_offset(table_values, width=width, max_rows=height)
        if next_row_offset is None and table_name in _INDEX_PREFILLED_APPEND_TABLES:
            next_row_offset = _first_empty_row_offset(
                table_values,
                width=width,
                max_rows=height,
                allow_prefilled_index_column=True,
            )
        if next_row_offset is None:
            raise ValueError(f"Named table is full; cannot append rows: {table_name}")
        if next_row_offset + len(normalized_rows) > height:
            raise ValueError(
                "Append would exceed named table capacity "
                f"({table_name}, remaining_rows={height - next_row_offset}, requested={len(normalized_rows)})."
            )

        start_row = bounds.row_start + next_row_offset
        end_row = start_row + len(normalized_rows) - 1
        target_range = _bounds_to_a1_subrange(
            bounds=bounds,
            start_row=start_row,
            end_row=end_row,
            start_col=bounds.col_start,
            end_col=bounds.col_end,
        )
        self._logger.info(
            "append_named_table_rows spreadsheet_id=%s table=%s start_row=%s rows=%s width=%s",
            spreadsheet_id,
            table_name,
            start_row,
            len(normalized_rows),
            width,
        )
        (
            self._sheets_service()
            .spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=target_range,
                valueInputOption="USER_ENTERED",
                body={"values": normalized_rows},
            )
            .execute()
        )

    def write_named_table(
        self,
        spreadsheet_id: str,
        table_name: str,
        rows: list[list[object]],
    ) -> None:
        if not rows:
            return
        bounds = self._resolve_named_table_bounds(
            spreadsheet_id=spreadsheet_id,
            table_name=table_name,
        )
        width, height = _bounds_size(bounds)
        if width <= 0 or height <= 0:
            raise ValueError(
                f"Named table range has invalid dimensions: {table_name}"
            )
        normalized_rows = _normalize_rows_for_table(rows, width=width)
        if len(normalized_rows) > height:
            raise ValueError(
                "Write would exceed named table capacity "
                f"({table_name}, max_rows={height}, requested={len(normalized_rows)})."
            )
        table_a1 = _bounds_to_a1_range(bounds)
        self._logger.info(
            "write_named_table spreadsheet_id=%s table=%s rows=%s width=%s",
            spreadsheet_id,
            table_name,
            len(normalized_rows),
            width,
        )
        (
            self._sheets_service()
            .spreadsheets()
            .values()
            .clear(
                spreadsheetId=spreadsheet_id,
                range=table_a1,
                body={},
            )
            .execute()
        )
        start_row = bounds.row_start
        end_row = start_row + len(normalized_rows) - 1
        target_range = _bounds_to_a1_subrange(
            bounds=bounds,
            start_row=start_row,
            end_row=end_row,
            start_col=bounds.col_start,
            end_col=bounds.col_end,
        )
        (
            self._sheets_service()
            .spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=target_range,
                valueInputOption="USER_ENTERED",
                body={"values": normalized_rows},
            )
            .execute()
        )

    def append_logbook_run(self, summary_row: list[object]) -> None:
        if not summary_row:
            return
        logbook_id = self._resolve_logbook_file_id(self._drive_service())
        target_range = f"{self.logbook_sheet_name}!A:Z"
        self._logger.info(
            "append_logbook_run logbook_id=%s row_len=%s",
            logbook_id,
            len(summary_row),
        )
        (
            self._sheets_service()
            .spreadsheets()
            .values()
            .append(
                spreadsheetId=logbook_id,
                range=target_range,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [summary_row]},
            )
            .execute()
        )

    def set_anyone_with_link_reader(self, spreadsheet_id: str) -> dict[str, object]:
        drive = self._drive_service()
        permissions_api = drive.permissions()
        existing_permissions = (
            permissions_api.list(
                fileId=spreadsheet_id,
                fields="permissions(id,type,role,allowFileDiscovery)",
                supportsAllDrives=True,
            ).execute()
        )
        for permission in existing_permissions.get("permissions", []):
            if permission.get("type") != "anyone":
                continue
            permission_id = str(permission.get("id") or "").strip()
            if not permission_id:
                continue
            role = str(permission.get("role") or "").strip().lower()
            allow_file_discovery = bool(permission.get("allowFileDiscovery"))
            if role == "reader" and not allow_file_discovery:
                self._logger.info(
                    "sheet_link_sharing_unchanged spreadsheet_id=%s permission_id=%s",
                    spreadsheet_id,
                    permission_id,
                )
                return {
                    "status": "unchanged",
                    "permission_id": permission_id,
                    "role": "reader",
                    "allow_file_discovery": False,
                }
            updated = (
                permissions_api.update(
                    fileId=spreadsheet_id,
                    permissionId=permission_id,
                    body={"role": "reader", "allowFileDiscovery": False},
                    fields="id,role,allowFileDiscovery",
                    supportsAllDrives=True,
                ).execute()
            )
            updated_permission_id = str(updated.get("id") or permission_id).strip()
            self._logger.info(
                "sheet_link_sharing_updated spreadsheet_id=%s permission_id=%s",
                spreadsheet_id,
                updated_permission_id,
            )
            return {
                "status": "updated",
                "permission_id": updated_permission_id,
                "role": str(updated.get("role") or "reader"),
                "allow_file_discovery": bool(updated.get("allowFileDiscovery")),
            }

        created = (
            permissions_api.create(
                fileId=spreadsheet_id,
                body={
                    "type": "anyone",
                    "role": "reader",
                    "allowFileDiscovery": False,
                },
                fields="id,role,allowFileDiscovery",
                supportsAllDrives=True,
            ).execute()
        )
        created_permission_id = str(created.get("id") or "").strip()
        self._logger.info(
            "sheet_link_sharing_created spreadsheet_id=%s permission_id=%s",
            spreadsheet_id,
            created_permission_id,
        )
        return {
            "status": "created",
            "permission_id": created_permission_id,
            "role": str(created.get("role") or "reader"),
            "allow_file_discovery": bool(created.get("allowFileDiscovery")),
        }

    def auto_resize_tabs(
        self,
        spreadsheet_id: str,
        tab_names: list[str],
    ) -> dict[str, int]:
        normalized_tabs: list[str] = []
        seen: set[str] = set()
        for raw_name in tab_names:
            name = str(raw_name or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            normalized_tabs.append(name)
        if not normalized_tabs:
            return {"tabs_requested": 0, "tabs_resized": 0, "requests_sent": 0}

        response = (
            self._sheets_service()
            .spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))",
            )
            .execute()
        )
        requests: list[dict[str, Any]] = []
        resized_tabs = 0
        for sheet in response.get("sheets", []):
            props = sheet.get("properties", {})
            title = str(props.get("title") or "").strip()
            if title not in seen:
                continue
            sheet_id = props.get("sheetId")
            if not isinstance(sheet_id, int):
                continue
            grid_props = props.get("gridProperties", {})
            row_count = grid_props.get("rowCount")
            col_count = grid_props.get("columnCount")
            if isinstance(col_count, int) and col_count > 0:
                requests.append(
                    {
                        "autoResizeDimensions": {
                            "dimensions": {
                                "sheetId": sheet_id,
                                "dimension": "COLUMNS",
                                "startIndex": 0,
                                "endIndex": col_count,
                            }
                        }
                    }
                )
            if isinstance(row_count, int) and row_count > 0:
                requests.append(
                    {
                        "autoResizeDimensions": {
                            "dimensions": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": 0,
                                "endIndex": row_count,
                            }
                        }
                    }
                )
            resized_tabs += 1

        if requests:
            (
                self._sheets_service()
                .spreadsheets()
                .batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": requests},
                )
                .execute()
            )
        self._logger.info(
            "auto_resize_tabs spreadsheet_id=%s tabs_requested=%s tabs_resized=%s requests_sent=%s",
            spreadsheet_id,
            len(normalized_tabs),
            resized_tabs,
            len(requests),
        )
        return {
            "tabs_requested": len(normalized_tabs),
            "tabs_resized": resized_tabs,
            "requests_sent": len(requests),
        }

    def inspect_workbook(self, spreadsheet_id: str) -> WorkbookInspection:
        schema = self._load_spreadsheet_schema(spreadsheet_id)
        return WorkbookInspection(
            sheet_names=tuple(sorted(schema.sheet_titles)),
            named_ranges=tuple(sorted(schema.named_ranges)),
        )

    def _sheets_service(self) -> Any:
        if self._sheets is None:
            self._sheets = build("sheets", "v4", credentials=self._load_credentials())
        return self._sheets

    def _drive_service(self) -> Any:
        if self._drive is None:
            self._drive = build("drive", "v3", credentials=self._load_credentials())
        return self._drive

    def _load_credentials(self) -> Any:
        if self._credentials is not None:
            return self._credentials

        auth_mode = self.settings.google_auth_mode.strip().lower()
        if auth_mode != "oauth":
            raise RuntimeError("V1 requires GOOGLE_AUTH_MODE=oauth for Sheets access.")

        oauth_client_file = Path(self.settings.google_oauth_client_secret_file)
        token_file = Path(self.settings.google_oauth_token_file)
        self._logger.info(
            "load_credentials mode=%s token_file=%s client_file=%s",
            auth_mode,
            token_file,
            oauth_client_file,
        )
        creds: UserCredentials | None = None
        if token_file.exists():
            if not _token_file_has_required_scopes(token_file):
                raise RuntimeError(
                    "Google OAuth token is missing required scopes for Drive+Sheets. "
                    "Delete token file and re-authorize with both scopes."
                )
            creds = UserCredentials.from_authorized_user_file(str(token_file), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not oauth_client_file.exists():
                    raise RuntimeError(
                        "Missing OAuth client secret file for Google Sheets authentication."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(oauth_client_file), SCOPES
                )
                creds = flow.run_local_server(
                    port=0,
                    open_browser=True,
                    access_type="offline",
                    prompt="consent",
                    include_granted_scopes="true",
                )
            token_file.write_text(creds.to_json(), encoding="utf-8")
        self._logger.info("load_credentials_done token_file=%s", token_file)

        self._credentials = creds
        return self._credentials

    def _resolve_template_file_id(self, drive: Any) -> str:
        if self._template_file_id:
            return self._template_file_id
        file_meta = self._find_drive_file_by_name(drive, self.settings.sheets_template_file)
        self._template_file_id = str(file_meta["id"])
        self._logger.info(
            "resolve_template_file_id name=%s id=%s",
            self.settings.sheets_template_file,
            self._template_file_id,
        )
        return self._template_file_id

    def _resolve_logbook_file_id(self, drive: Any) -> str:
        if self._logbook_file_id:
            return self._logbook_file_id
        file_meta = self._find_drive_file_by_name(drive, self.settings.sheets_logbook_file)
        self._logbook_file_id = str(file_meta["id"])
        self._logger.info(
            "resolve_logbook_file_id name=%s id=%s",
            self.settings.sheets_logbook_file,
            self._logbook_file_id,
        )
        return self._logbook_file_id

    def _find_drive_file_by_name(self, drive: Any, name: str) -> dict[str, Any]:
        for candidate in self._candidate_names(name):
            escaped = candidate.replace("'", "\\'")
            query = f"name = '{escaped}' and trashed = false"
            response = (
                drive.files()
                .list(
                    q=query,
                    fields="files(id,name,mimeType,modifiedTime)",
                    pageSize=100,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            files = response.get("files", [])
            self._logger.info(
                "find_drive_file candidate=%s matches=%s",
                candidate,
                len(files),
            )
            if not files:
                continue
            files.sort(
                key=lambda item: (
                    item.get("mimeType") != "application/vnd.google-apps.spreadsheet",
                    item.get("modifiedTime", ""),
                ),
                reverse=True,
            )
            return files[0]
        raise RuntimeError(f"Drive file not found by name: {name}")

    def _candidate_names(self, name: str) -> tuple[str, ...]:
        clean = name.strip()
        if not clean:
            return ()
        candidates = [clean]
        if clean.endswith(".xlsx"):
            candidates.append(clean[:-5])
        else:
            candidates.append(f"{clean}.xlsx")
        deduped = []
        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            deduped.append(candidate)
        return tuple(deduped)

    def _validate_named_range_write_targets(
        self,
        *,
        spreadsheet_id: str,
        values: dict[str, object],
    ) -> dict[str, object]:
        known_ranges = self._load_named_ranges(spreadsheet_id)
        unknown = sorted(name for name in values if name not in known_ranges)
        if unknown:
            raise ValueError(
                "Unknown named ranges for write_named_ranges: "
                f"{', '.join(unknown[:10])}"
            )

        blocked = sorted(name for name in values if _is_formula_owned_name(name))
        if blocked:
            raise ValueError(
                "Writes to formula-owned named ranges are blocked: "
                f"{', '.join(blocked[:10])}"
            )
        return values

    def _coerce_named_range_write_shapes(
        self,
        *,
        spreadsheet_id: str,
        values: dict[str, object],
    ) -> dict[str, list[list[object]]]:
        schema = self._load_spreadsheet_schema(spreadsheet_id)
        normalized: dict[str, list[list[object]]] = {}
        for name, raw_value in values.items():
            matrix = _normalize_sheet_values(raw_value)
            bounds = schema.named_range_bounds.get(name)
            if bounds is None:
                normalized[name] = matrix
                continue
            target_width, target_height = _bounds_size(bounds)
            if target_width <= 0 or target_height <= 0:
                normalized[name] = matrix
                continue
            coerced, mode = _coerce_matrix_for_named_range(
                name=name,
                matrix=matrix,
                target_rows=target_height,
                target_cols=target_width,
            )
            if mode:
                self._logger.info(
                    "write_named_ranges_shape_coerced range=%s mode=%s before=%s after=%s",
                    name,
                    mode,
                    _matrix_shape_summary(matrix),
                    _matrix_shape_summary(coerced),
                )
            normalized[name] = coerced
        return normalized

    def _resolve_named_table_bounds(
        self,
        *,
        spreadsheet_id: str,
        table_name: str,
    ) -> _RangeBounds:
        normalized = table_name.strip()
        if not normalized:
            raise ValueError("table_name cannot be empty.")
        if _is_formula_owned_name(normalized):
            raise ValueError(f"Named table cannot use formula-owned range: {normalized}")
        schema = self._load_spreadsheet_schema(spreadsheet_id)
        bounds = schema.named_range_bounds.get(normalized)
        if bounds is None:
            raise ValueError(f"Unknown named table range: {normalized}")
        if bounds.row_start is None or bounds.row_end is None:
            raise ValueError(f"Named table range must be row-bounded: {normalized}")
        if bounds.col_start is None or bounds.col_end is None:
            raise ValueError(f"Named table range must be column-bounded: {normalized}")
        return bounds

    def _load_named_ranges(self, spreadsheet_id: str) -> set[str]:
        cached = self._named_ranges_cache.get(spreadsheet_id)
        if cached is not None:
            return cached

        schema = self._load_spreadsheet_schema(spreadsheet_id)
        named_ranges = set(schema.named_ranges)
        self._named_ranges_cache[spreadsheet_id] = named_ranges
        return named_ranges

    def _load_spreadsheet_schema(self, spreadsheet_id: str) -> _SpreadsheetSchema:
        cached = self._schema_cache.get(spreadsheet_id)
        if cached is not None:
            return cached

        response = (
            self._sheets_service()
            .spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                fields=(
                    "namedRanges(name,range(sheetId,startRowIndex,endRowIndex,startColumnIndex,endColumnIndex)),"
                    "sheets(properties(sheetId,title))"
                ),
            )
            .execute()
        )
        sheet_id_to_title: dict[int, str] = {}
        sheet_titles: set[str] = set()
        for sheet in response.get("sheets", []):
            props = sheet.get("properties", {})
            title = str(props.get("title") or "").strip()
            sheet_id = props.get("sheetId")
            if not title:
                continue
            sheet_titles.add(title)
            if isinstance(sheet_id, int):
                sheet_id_to_title[sheet_id] = title

        named_ranges: set[str] = set()
        named_range_bounds: dict[str, _RangeBounds] = {}
        formula_owned_bounds: list[_RangeBounds] = []
        for entry in response.get("namedRanges", []):
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            named_ranges.add(name)
            grid = entry.get("range")
            if isinstance(grid, dict):
                sheet_id = grid.get("sheetId")
                if isinstance(sheet_id, int):
                    sheet_title = sheet_id_to_title.get(sheet_id)
                    if sheet_title:
                        bounds = _grid_range_to_bounds(sheet_title, grid)
                        if bounds is not None:
                            named_range_bounds[name] = bounds
            if not _is_formula_owned_name(name):
                continue
            bounds = named_range_bounds.get(name)
            if bounds is not None:
                formula_owned_bounds.append(bounds)

        schema = _SpreadsheetSchema(
            sheet_titles=frozenset(sheet_titles),
            named_ranges=frozenset(named_ranges),
            named_range_bounds=named_range_bounds,
            formula_owned_bounds=tuple(formula_owned_bounds),
        )
        self._schema_cache[spreadsheet_id] = schema
        self._named_ranges_cache[spreadsheet_id] = set(named_ranges)
        self._logger.info(
            "load_spreadsheet_schema spreadsheet_id=%s tabs=%s named_ranges=%s bounded_named_ranges=%s formula_owned=%s",
            spreadsheet_id,
            len(sheet_titles),
            len(named_ranges),
            len(named_range_bounds),
            len(formula_owned_bounds),
        )
        return schema


def _normalize_sheet_values(value: object) -> list[list[object]]:
    if isinstance(value, list):
        if not value:
            return [[]]
        if all(isinstance(row, list) for row in value):
            return [list(row) for row in value]  # type: ignore[arg-type]
        return [list(value)]  # type: ignore[arg-type]
    return [[value]]


def _coerce_matrix_for_named_range(
    *,
    name: str,
    matrix: list[list[object]],
    target_rows: int,
    target_cols: int,
) -> tuple[list[list[object]], str | None]:
    if target_rows <= 0 or target_cols <= 0:
        return matrix, None
    flattened = _flatten_matrix_values(matrix)
    cell_count = len(flattened)
    expected_cells = target_rows * target_cols
    if target_rows == 1 or target_cols == 1:
        expected_len = max(target_rows, target_cols)
        if cell_count != expected_len:
            raise ValueError(
                "Named range write shape mismatch for "
                f"{name}: expected {target_rows}x{target_cols} "
                f"({expected_len} cells), received {_matrix_shape_summary(matrix)} "
                f"({cell_count} cells)."
            )
        if target_rows == 1:
            coerced = [flattened]
            mode = None if _matrix_shape_summary(matrix) == _matrix_shape_summary(coerced) else "column_to_row"
            return coerced, mode
        coerced = [[value] for value in flattened]
        mode = None if _matrix_shape_summary(matrix) == _matrix_shape_summary(coerced) else "row_to_column"
        return coerced, mode

    if cell_count != expected_cells:
        raise ValueError(
            "Named range write shape mismatch for "
            f"{name}: expected {target_rows}x{target_cols} "
            f"({expected_cells} cells), received {_matrix_shape_summary(matrix)} "
            f"({cell_count} cells)."
        )
    if len(matrix) != target_rows:
        raise ValueError(
            "Named range write shape mismatch for "
            f"{name}: expected {target_rows} rows, received {len(matrix)} "
            f"({_matrix_shape_summary(matrix)})."
        )
    for row in matrix:
        if len(row) != target_cols:
            raise ValueError(
                "Named range write shape mismatch for "
                f"{name}: expected row width {target_cols}, received ragged matrix "
                f"({_matrix_shape_summary(matrix)})."
            )
    return [list(row) for row in matrix], None


def _flatten_matrix_values(matrix: list[list[object]]) -> list[object]:
    flattened: list[object] = []
    for row in matrix:
        if isinstance(row, list):
            flattened.extend(row)
        else:
            flattened.append(row)
    return flattened


def _matrix_shape_summary(matrix: list[list[object]]) -> str:
    row_count = len(matrix)
    if row_count == 0:
        return "0x0"
    widths = sorted({len(row) if isinstance(row, list) else 1 for row in matrix})
    if len(widths) == 1:
        return f"{row_count}x{widths[0]}"
    return f"{row_count}x{max(widths)}(ragged)"


def _normalize_named_range_list(names: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for name in names:
        candidate = str(name).strip()
        if not candidate:
            continue
        if "!" in candidate or ":" in candidate:
            raise ValueError(
                f"Named-range-only tool received non-named target: {candidate}"
            )
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


def _resolve_named_range_targets(
    *,
    names: list[str],
    known_ranges: set[str],
) -> tuple[dict[str, str], list[str]]:
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for name in names:
        aliases = _NAMED_RANGE_ALIASES.get(name, (name,))
        selected = next((alias for alias in aliases if alias in known_ranges), None)
        if selected is None:
            missing.append(name)
            continue
        resolved[name] = selected
    return resolved, missing


def _normalize_rows_for_table(rows: list[list[object]], *, width: int) -> list[list[object]]:
    normalized: list[list[object]] = []
    for row in rows:
        if isinstance(row, list):
            values = list(row)
        else:
            values = [row]
        if len(values) > width:
            raise ValueError(
                f"Table row width exceeds table range width (row_width={len(values)} > width={width})."
            )
        if len(values) < width:
            values.extend([""] * (width - len(values)))
        normalized.append(values)
    return normalized


def _bounds_size(bounds: _RangeBounds) -> tuple[int, int]:
    if (
        bounds.col_start is None
        or bounds.col_end is None
        or bounds.row_start is None
        or bounds.row_end is None
    ):
        return (0, 0)
    width = bounds.col_end - bounds.col_start + 1
    height = bounds.row_end - bounds.row_start + 1
    return (width, height)


def _bounds_to_a1_range(bounds: _RangeBounds) -> str:
    if (
        bounds.col_start is None
        or bounds.col_end is None
        or bounds.row_start is None
        or bounds.row_end is None
    ):
        raise ValueError("A1 conversion requires bounded rows and columns.")
    start_col = _index_to_column(bounds.col_start)
    end_col = _index_to_column(bounds.col_end)
    return (
        f"{_quote_sheet_name(bounds.sheet)}!"
        f"{start_col}{bounds.row_start}:{end_col}{bounds.row_end}"
    )


def _bounds_to_a1_subrange(
    *,
    bounds: _RangeBounds,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
) -> str:
    if start_row > end_row:
        raise ValueError("start_row cannot be after end_row.")
    if start_col > end_col:
        raise ValueError("start_col cannot be after end_col.")
    if (
        bounds.row_start is None
        or bounds.row_end is None
        or bounds.col_start is None
        or bounds.col_end is None
    ):
        raise ValueError("Named table bounds are not fully bounded.")
    if start_row < bounds.row_start or end_row > bounds.row_end:
        raise ValueError("Requested subrange exceeds table row bounds.")
    if start_col < bounds.col_start or end_col > bounds.col_end:
        raise ValueError("Requested subrange exceeds table column bounds.")
    return (
        f"{_quote_sheet_name(bounds.sheet)}!"
        f"{_index_to_column(start_col)}{start_row}:{_index_to_column(end_col)}{end_row}"
    )


def _first_empty_row_offset(
    values: list[list[object]],
    *,
    width: int,
    max_rows: int,
    allow_prefilled_index_column: bool = False,
) -> int | None:
    for idx in range(max_rows):
        row = values[idx] if idx < len(values) else []
        if _row_is_empty(
            row,
            width=width,
            allow_prefilled_index_column=allow_prefilled_index_column,
        ):
            return idx
    return None


def _row_is_empty(
    row: list[object],
    *,
    width: int,
    allow_prefilled_index_column: bool = False,
) -> bool:
    if not row:
        return True
    if allow_prefilled_index_column and width >= 2:
        first = row[0] if row else None
        rest = [row[idx] if idx < len(row) else "" for idx in range(1, width)]
        if _looks_like_prefilled_index(first) and all(_is_blank_cell(cell) for cell in rest):
            return True
    for idx in range(min(len(row), width)):
        if not _is_blank_cell(row[idx]):
            return False
    return True


def _is_blank_cell(value: object) -> bool:
    return value is None or str(value).strip() == ""


def _looks_like_prefilled_index(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    text = str(value).strip()
    if not text:
        return False
    try:
        float(text)
        return True
    except ValueError:
        return False


def _quote_sheet_name(sheet_name: str) -> str:
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'"


def _is_formula_owned_name(name: str) -> bool:
    normalized = name.strip().lower()
    return normalized.startswith("out_") or normalized.startswith("calc_")


def _grid_range_to_bounds(sheet_title: str, grid: dict[str, Any]) -> _RangeBounds | None:
    row_start_raw = grid.get("startRowIndex")
    row_end_raw = grid.get("endRowIndex")
    col_start_raw = grid.get("startColumnIndex")
    col_end_raw = grid.get("endColumnIndex")

    row_start = int(row_start_raw) + 1 if isinstance(row_start_raw, int) else None
    row_end = int(row_end_raw) if isinstance(row_end_raw, int) else None
    col_start = int(col_start_raw) + 1 if isinstance(col_start_raw, int) else None
    col_end = int(col_end_raw) if isinstance(col_end_raw, int) else None

    if row_start is None and row_end is None and col_start is None and col_end is None:
        return None
    return _RangeBounds(
        sheet=sheet_title,
        row_start=row_start,
        row_end=row_end,
        col_start=col_start,
        col_end=col_end,
    )


def _parse_a1_range(raw_value: str) -> _RangeBounds | None:
    candidate = raw_value.strip()
    if "!" not in candidate:
        return None
    sheet_part, ref_part = candidate.split("!", 1)
    sheet = _parse_sheet_name(sheet_part)
    if not sheet:
        return None
    ref = ref_part.strip()
    if not ref:
        return None

    if ":" in ref:
        left_token, right_token = ref.split(":", 1)
    else:
        left_token = ref
        right_token = ref

    left = _parse_a1_token(left_token.strip())
    right = _parse_a1_token(right_token.strip())
    if left is None or right is None:
        return None
    if left["kind"] != right["kind"]:
        return None

    kind = left["kind"]
    if kind == "cell":
        return _RangeBounds(
            sheet=sheet,
            row_start=min(left["row"], right["row"]),
            row_end=max(left["row"], right["row"]),
            col_start=min(left["col"], right["col"]),
            col_end=max(left["col"], right["col"]),
        )
    if kind == "col":
        return _RangeBounds(
            sheet=sheet,
            row_start=None,
            row_end=None,
            col_start=min(left["col"], right["col"]),
            col_end=max(left["col"], right["col"]),
        )
    if kind == "row":
        return _RangeBounds(
            sheet=sheet,
            row_start=min(left["row"], right["row"]),
            row_end=max(left["row"], right["row"]),
            col_start=None,
            col_end=None,
        )
    return None


def _parse_sheet_name(raw_sheet: str) -> str:
    token = raw_sheet.strip()
    if not token:
        return ""
    if token.startswith("'") or token.endswith("'"):
        if len(token) < 2 or not token.startswith("'") or not token.endswith("'"):
            return ""
        token = token[1:-1].replace("''", "'")
    return token.strip()


def _parse_a1_token(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    cell_match = _A1_CELL_RE.fullmatch(token)
    if cell_match:
        return {
            "kind": "cell",
            "col": _column_to_index(cell_match.group(1)),
            "row": int(cell_match.group(2)),
        }
    col_match = _A1_COL_RE.fullmatch(token)
    if col_match:
        return {
            "kind": "col",
            "col": _column_to_index(col_match.group(1)),
            "row": None,
        }
    row_match = _A1_ROW_RE.fullmatch(token)
    if row_match:
        return {
            "kind": "row",
            "col": None,
            "row": int(row_match.group(1)),
        }
    return None


def _column_to_index(col: str) -> int:
    value = 0
    for ch in col.upper():
        if not ("A" <= ch <= "Z"):
            raise ValueError(f"Invalid column token: {col}")
        value = value * 26 + (ord(ch) - ord("A") + 1)
    return value


def _index_to_column(index: int) -> str:
    if index <= 0:
        raise ValueError(f"Invalid 1-based column index: {index}")
    value = index
    letters: list[str] = []
    while value > 0:
        value, rem = divmod(value - 1, 26)
        letters.append(chr(ord("A") + rem))
    return "".join(reversed(letters))


def _overlaps_formula_owned(
    candidate: _RangeBounds,
    protected: tuple[_RangeBounds, ...],
) -> bool:
    for protected_range in protected:
        if protected_range.sheet != candidate.sheet:
            continue
        if _axis_overlaps(
            candidate.row_start,
            candidate.row_end,
            protected_range.row_start,
            protected_range.row_end,
        ) and _axis_overlaps(
            candidate.col_start,
            candidate.col_end,
            protected_range.col_start,
            protected_range.col_end,
        ):
            return True
    return False


def _axis_overlaps(
    first_start: int | None,
    first_end: int | None,
    second_start: int | None,
    second_end: int | None,
) -> bool:
    first_low = -10**12 if first_start is None else first_start
    first_high = 10**12 if first_end is None else first_end
    second_low = -10**12 if second_start is None else second_start
    second_high = 10**12 if second_end is None else second_end
    return not (first_high < second_low or second_high < first_low)


def _required_scopes_present(scopes: list[str] | None) -> bool:
    if not scopes:
        return False
    return set(SCOPES).issubset(set(scopes))


def _token_file_has_required_scopes(token_file: Path) -> bool:
    try:
        payload = json.loads(token_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    scopes_value = payload.get("scopes")
    scopes: list[str]
    if isinstance(scopes_value, list):
        scopes = [str(item) for item in scopes_value]
    elif isinstance(scopes_value, str):
        scopes = [item.strip() for item in scopes_value.split(" ") if item.strip()]
    else:
        single = payload.get("scope")
        if isinstance(single, str):
            scopes = [item.strip() for item in single.split(" ") if item.strip()]
        else:
            scopes = []
    return _required_scopes_present(scopes)
