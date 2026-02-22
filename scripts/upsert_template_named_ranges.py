#!/usr/bin/env python3
"""Upsert phase-v1 named ranges on the Google Sheets valuation template."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
SCOPES = [SHEETS_SCOPE, DRIVE_SCOPE]


@dataclass(frozen=True)
class NamedRangeSpec:
    name: str
    sheet: str
    start_row: int
    end_row: int
    start_col: int
    end_col: int


@dataclass(frozen=True)
class _SheetMeta:
    sheet_id: int
    row_count: int
    column_count: int


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"").strip("'")
        os.environ.setdefault(key, value)


def _required_scopes_present(scopes: list[str] | None) -> bool:
    if not scopes:
        return False
    return set(SCOPES).issubset(set(scopes))


def load_credentials() -> Any:
    """Load service-account or OAuth user credentials with Drive+Sheets scopes."""
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    cred_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if cred_path:
        return service_account.Credentials.from_service_account_file(
            cred_path, scopes=SCOPES
        )

    if cred_json:
        return service_account.Credentials.from_service_account_info(
            json.loads(cred_json), scopes=SCOPES
        )

    oauth_client_file = Path(
        os.getenv("GOOGLE_OAUTH_CLIENT_SECRET_FILE", "credentials.json")
    )
    token_file = Path(os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "token.json"))

    creds: UserCredentials | None = None
    if token_file.exists():
        creds = UserCredentials.from_authorized_user_file(str(token_file), SCOPES)
        if not _required_scopes_present(creds.scopes):
            creds = None

    if creds and not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None
        else:
            creds = None

    if not creds:
        if not oauth_client_file.exists():
            raise RuntimeError(
                "Missing credentials. Provide service-account credentials via "
                "GOOGLE_APPLICATION_CREDENTIALS/GOOGLE_SERVICE_ACCOUNT_JSON, "
                "or provide OAuth client secrets at credentials.json."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(oauth_client_file), SCOPES)
        creds = flow.run_local_server(
            port=0,
            open_browser=True,
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return creds


def _build_drive_query(name: str) -> str:
    escaped = name.replace("'", "\\'")
    return f"name = '{escaped}' and trashed = false"


def _find_drive_file_by_name(drive: Any, name: str) -> dict[str, Any]:
    candidate_names = [name]
    if name.endswith(".xlsx"):
        candidate_names.append(name[:-5])
    else:
        candidate_names.append(f"{name}.xlsx")

    files: list[dict[str, Any]] = []
    for candidate in candidate_names:
        response = (
            drive.files()
            .list(
                q=_build_drive_query(candidate),
                fields="files(id,name,mimeType,modifiedTime,webViewLink)",
                pageSize=100,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        files = response.get("files", [])
        if files:
            break
    if not files:
        raise RuntimeError(f"Could not find Drive file by name: {name}")

    files.sort(
        key=lambda item: (
            item.get("mimeType") != "application/vnd.google-apps.spreadsheet",
            item.get("modifiedTime", ""),
        ),
        reverse=True,
    )
    return files[0]


def _grid_range(spec: NamedRangeSpec, sheet_ids: dict[str, int]) -> dict[str, int]:
    sheet_id = sheet_ids.get(spec.sheet)
    if sheet_id is None:
        raise ValueError(f"Unknown sheet for named range {spec.name}: {spec.sheet}")
    return {
        "sheetId": sheet_id,
        "startRowIndex": spec.start_row - 1,
        "endRowIndex": spec.end_row,
        "startColumnIndex": spec.start_col - 1,
        "endColumnIndex": spec.end_col,
    }


def _same_grid(a: dict[str, Any], b: dict[str, Any]) -> bool:
    keys = (
        "sheetId",
        "startRowIndex",
        "endRowIndex",
        "startColumnIndex",
        "endColumnIndex",
    )
    return all(int(a.get(k, -1)) == int(b.get(k, -2)) for k in keys)


def _build_sheet_meta(meta: dict[str, Any]) -> dict[str, _SheetMeta]:
    output: dict[str, _SheetMeta] = {}
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties", {})
        title = str(props.get("title") or "").strip()
        sheet_id = props.get("sheetId")
        grid = props.get("gridProperties", {})
        row_count = grid.get("rowCount")
        col_count = grid.get("columnCount")
        if (
            title
            and isinstance(sheet_id, int)
            and isinstance(row_count, int)
            and isinstance(col_count, int)
        ):
            output[title] = _SheetMeta(
                sheet_id=sheet_id,
                row_count=row_count,
                column_count=col_count,
            )
    return output


def _phase_v1_range_specs() -> tuple[NamedRangeSpec, ...]:
    return (
        NamedRangeSpec("comps_header", "Comps", 7, 7, 2, 52),
        NamedRangeSpec("comps_firstrow", "Comps", 8, 8, 2, 52),
        NamedRangeSpec("comps_table", "Comps", 8, 200, 2, 52),
        NamedRangeSpec("comps_table_full", "Comps", 7, 200, 2, 52),
        NamedRangeSpec("comps_peer_tickers", "Comps", 8, 200, 2, 2),
        NamedRangeSpec("comps_peer_names", "Comps", 8, 200, 3, 3),
        NamedRangeSpec("comps_multiples_header", "Comps", 7, 7, 3, 51),
        NamedRangeSpec("comps_multiples_values", "Comps", 8, 200, 3, 51),
        NamedRangeSpec("comps_method_note", "Comps", 6, 6, 3, 3),
        NamedRangeSpec("comps_peer_count", "Comps", 4, 4, 6, 6),
        NamedRangeSpec("comps_multiple_count", "Comps", 5, 5, 6, 6),
        NamedRangeSpec("sources_header", "Sources", 6, 6, 2, 12),
        NamedRangeSpec("sources_firstrow", "Sources", 7, 7, 2, 12),
        NamedRangeSpec("sources_table", "Sources", 7, 400, 2, 12),
        NamedRangeSpec("log_actions_table", "Agent Log", 17, 216, 2, 10),
        NamedRangeSpec("log_assumptions_table", "Agent Log", 221, 246, 2, 11),
        NamedRangeSpec("log_story_table", "Agent Log", 251, 286, 2, 10),
        NamedRangeSpec("checks_statuses", "Checks", 5, 17, 3, 3),
        NamedRangeSpec("OUT_WACC", "Output", 9, 9, 3, 3),
        NamedRangeSpec("story_grid_header", "Story", 23, 23, 2, 7),
        NamedRangeSpec("story_grid_rows", "Story", 24, 26, 2, 7),
        NamedRangeSpec("story_grid_citations", "Story", 24, 26, 7, 7),
        NamedRangeSpec("story_memo_hooks", "Story", 28, 30, 3, 7),
        NamedRangeSpec("story_core_narrative_rows", "Story", 24, 26, 3, 3),
        NamedRangeSpec("story_linked_operating_driver_rows", "Story", 24, 26, 4, 4),
        NamedRangeSpec("story_kpi_to_track_rows", "Story", 24, 26, 5, 5),
    )


def run(args: argparse.Namespace) -> int:
    if args.env_file:
        _load_env_file(Path(args.env_file))

    template_name = args.template_name or os.getenv(
        "SHEETS_TEMPLATE_FILE",
        "Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx",
    )

    creds = load_credentials()
    drive = build("drive", "v3", credentials=creds)
    sheets = build("sheets", "v4", credentials=creds)

    template = _find_drive_file_by_name(drive, template_name)
    spreadsheet_id = template["id"]

    print(f"template_name={template.get('name')}")
    print(f"spreadsheet_id={spreadsheet_id}")

    meta = (
        sheets.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields=(
                "sheets(properties(sheetId,title,gridProperties(rowCount,columnCount))),"
                "namedRanges(namedRangeId,name,range(sheetId,startRowIndex,endRowIndex,startColumnIndex,endColumnIndex))"
            ),
        )
        .execute()
    )

    sheet_meta = _build_sheet_meta(meta)
    sheet_ids = {title: info.sheet_id for title, info in sheet_meta.items()}

    existing_by_name: dict[str, dict[str, Any]] = {}
    existing_by_name_casefold: dict[str, dict[str, Any]] = {}
    for named in meta.get("namedRanges", []):
        name = str(named.get("name") or "").strip()
        if name:
            existing_by_name[name] = named
            existing_by_name_casefold[name.casefold()] = named

    requests: list[dict[str, Any]] = []
    dimension_requests: list[dict[str, Any]] = []
    created = 0
    updated = 0
    unchanged = 0

    required_rows: dict[str, int] = {}
    required_cols: dict[str, int] = {}
    for spec in _phase_v1_range_specs():
        required_rows[spec.sheet] = max(required_rows.get(spec.sheet, 0), spec.end_row)
        required_cols[spec.sheet] = max(required_cols.get(spec.sheet, 0), spec.end_col)

    for sheet_name, max_col in sorted(required_cols.items()):
        info = sheet_meta.get(sheet_name)
        if info is None:
            raise ValueError(f"Unknown sheet required by range specs: {sheet_name}")
        if info.column_count < max_col:
            dimension_requests.append(
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": info.sheet_id,
                            "gridProperties": {"columnCount": max_col},
                        },
                        "fields": "gridProperties.columnCount",
                    }
                }
            )
            print(f"EXPAND_COLS {sheet_name} {info.column_count}->{max_col}")

    for sheet_name, max_row in sorted(required_rows.items()):
        info = sheet_meta.get(sheet_name)
        if info is None:
            raise ValueError(f"Unknown sheet required by range specs: {sheet_name}")
        if info.row_count < max_row:
            dimension_requests.append(
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": info.sheet_id,
                            "gridProperties": {"rowCount": max_row},
                        },
                        "fields": "gridProperties.rowCount",
                    }
                }
            )
            print(f"EXPAND_ROWS {sheet_name} {info.row_count}->{max_row}")

    for spec in _phase_v1_range_specs():
        target_grid = _grid_range(spec, sheet_ids)
        existing = existing_by_name.get(spec.name)
        if existing is None:
            existing = existing_by_name_casefold.get(spec.name.casefold())

        if existing is None:
            requests.append(
                {
                    "addNamedRange": {
                        "namedRange": {
                            "name": spec.name,
                            "range": target_grid,
                        }
                    }
                }
            )
            created += 1
            print(f"ADD {spec.name}")
            continue

        current_grid = existing.get("range", {})
        if _same_grid(current_grid, target_grid):
            unchanged += 1
            print(f"KEEP {spec.name}")
            continue

        requests.append(
            {
                "updateNamedRange": {
                    "namedRange": {
                        "namedRangeId": existing["namedRangeId"],
                        "name": spec.name,
                        "range": target_grid,
                    },
                    "fields": "name,range",
                }
            }
        )
        updated += 1
        print(f"UPDATE {spec.name}")

    if args.dry_run:
        print(
            "dry_run=true "
            f"create_or_update_requests={len(requests)} "
            f"dimension_requests={len(dimension_requests)} "
            f"created={created} updated={updated} unchanged={unchanged}"
        )
        return 0

    if dimension_requests:
        (
            sheets.spreadsheets()
            .batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": dimension_requests},
            )
            .execute()
        )
    if requests:
        (
            sheets.spreadsheets()
            .batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests},
            )
            .execute()
        )

    print(
        "done "
        f"created={created} updated={updated} unchanged={unchanged} "
        f"dimension_requests_sent={len(dimension_requests)} create_or_update_requests_sent={len(requests)}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Optional env file path (default: .env).",
    )
    parser.add_argument(
        "--template-name",
        default="",
        help="Drive template file name override.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned updates without writing.",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
