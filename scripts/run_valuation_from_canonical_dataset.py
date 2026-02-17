#!/usr/bin/env python3
"""Run valuation on a Google Sheets template from a canonical dataset artifact."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
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

OUTPUT_RANGES = [
    "out_value_per_share",
    "out_equity_value",
    "out_enterprise_value",
    "out_wacc",
    "out_terminal_g",
    "out_diluted_shares",
    "out_run_id",
]


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


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


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


def _make_run_name(ticker: str, template_name: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ticker.upper()}_{ts}_{template_name}"


def _copy_template(
    drive: Any, template_file_id: str, new_name: str
) -> dict[str, Any]:
    copy = (
        drive.files()
        .copy(
            fileId=template_file_id,
            body={"name": new_name},
            fields="id,name,mimeType,webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    if copy.get("mimeType") != "application/vnd.google-apps.spreadsheet":
        raise RuntimeError(
            "Template copy is not a Google Spreadsheet. "
            "Open the template in Google Sheets first so formulas/named ranges are supported."
        )
    return copy


def _write_named_ranges(sheets: Any, spreadsheet_id: str, values: dict[str, Any]) -> None:
    data = [{"range": key, "values": [[value]]} for key, value in values.items()]
    (
        sheets.spreadsheets()
        .values()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": data},
        )
        .execute()
    )


def _enable_iterative_calculation(sheets: Any, spreadsheet_id: str) -> None:
    (
        sheets.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "updateSpreadsheetProperties": {
                            "properties": {
                                "iterativeCalculationSettings": {
                                    "maxIterations": 200,
                                    "convergenceThreshold": 0.000001,
                                }
                            },
                            "fields": "iterativeCalculationSettings",
                        }
                    }
                ]
            },
        )
        .execute()
    )


def _read_outputs(sheets: Any, spreadsheet_id: str) -> dict[str, Any]:
    response = (
        sheets.spreadsheets()
        .values()
        .batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=OUTPUT_RANGES,
            valueRenderOption="UNFORMATTED_VALUE",
        )
        .execute()
    )
    output: dict[str, Any] = {}
    returned_ranges = response.get("valueRanges", [])
    for expected_name, entry in zip(OUTPUT_RANGES, returned_ranges):
        values = entry.get("values", [])
        output[expected_name] = values[0][0] if values and values[0] else None
    return output


def _poll_outputs(sheets: Any, spreadsheet_id: str, timeout_seconds: int = 60) -> dict[str, Any]:
    start = time.time()
    last: dict[str, Any] = {}
    while time.time() - start <= timeout_seconds:
        last = _read_outputs(sheets, spreadsheet_id)
        value_per_share = last.get("out_value_per_share")
        if value_per_share is not None and value_per_share != "":
            return last
        time.sleep(2)
    return last


def _run_guardrails(outputs: dict[str, Any], sheets_inputs: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    wacc = outputs.get("out_wacc")
    terminal_g = outputs.get("out_terminal_g")
    rf = sheets_inputs.get("inp_rf")
    if isinstance(wacc, (int, float)) and isinstance(terminal_g, (int, float)):
        if not wacc > terminal_g:
            issues.append(f"Hard fail: out_wacc ({wacc}) must be greater than out_terminal_g ({terminal_g}).")
    if isinstance(terminal_g, (int, float)) and isinstance(rf, (int, float)):
        if terminal_g > rf:
            issues.append(f"Warning: out_terminal_g ({terminal_g}) is greater than inp_rf ({rf}).")
    if outputs.get("out_value_per_share") in (None, ""):
        issues.append("Hard fail: out_value_per_share is blank.")
    return issues


def _append_logbook_row(
    sheets: Any,
    logbook_spreadsheet_id: str,
    row: list[Any],
    logbook_sheet_name: str,
    target_columns_range: str = "A:Z",
) -> None:
    target_range = f"{logbook_sheet_name}!{target_columns_range}"
    (
        sheets.spreadsheets()
        .values()
        .append(
            spreadsheetId=logbook_spreadsheet_id,
            range=target_range,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        )
        .execute()
    )


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _a1_col(col_index_zero_based: int) -> str:
    n = col_index_zero_based + 1
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def _find_runs_header_row(
    sheets: Any,
    spreadsheet_id: str,
    sheet_name: str,
) -> tuple[int, list[str]]:
    values = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A1:Z30")
        .execute()
        .get("values", [])
    )
    for idx, row in enumerate(values, start=1):
        normalized = {_normalize_header(cell) for cell in row if cell}
        if "runid" in normalized and "spreadsheetid" in normalized:
            padded = row + [""] * (26 - len(row))
            return idx, padded[:26]
    raise RuntimeError(
        f"Could not find logbook header row in {sheet_name}. "
        "Expected headers including Run ID and Spreadsheet ID."
    )


def _build_runs_row_from_headers(
    headers: list[str],
    values_by_header: dict[str, Any],
) -> list[Any]:
    row: list[Any] = []
    for header in headers:
        key = _normalize_header(header)
        row.append(values_by_header.get(key, ""))
    return row


def _repair_legacy_misaligned_runs_rows(
    sheets: Any,
    spreadsheet_id: str,
    sheet_name: str,
    header_row_idx: int,
    headers: list[str],
) -> int:
    run_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "runid"),
        None,
    )
    start_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "starttsutc"),
        None,
    )
    end_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "endtsutc"),
        None,
    )
    ticker_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "ticker"),
        None,
    )
    company_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "company"),
        None,
    )
    template_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "templatev"),
        None,
    )
    agent_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "agentv"),
        None,
    )
    model_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "model"),
        None,
    )
    status_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "status"),
        None,
    )
    value_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "valueshare"),
        None,
    )
    wacc_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "wacc"),
        None,
    )
    g_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "g"),
        None,
    )
    tokens_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "tokens"),
        None,
    )
    cost_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "costusd"),
        None,
    )
    spreadsheet_id_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "spreadsheetid"),
        None,
    )
    share_link_col_idx = next(
        (i for i, h in enumerate(headers) if _normalize_header(h) == "sharelink"),
        None,
    )

    if None in {
        run_col_idx,
        start_col_idx,
        end_col_idx,
        ticker_col_idx,
        status_col_idx,
        value_col_idx,
        wacc_col_idx,
        g_col_idx,
        spreadsheet_id_col_idx,
        share_link_col_idx,
    }:
        return 0

    values = (
        sheets.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A{header_row_idx + 1}:Z1000",
            valueRenderOption="UNFORMATTED_VALUE",
        )
        .execute()
        .get("values", [])
    )

    updates: list[dict[str, Any]] = []
    run_id_pattern = re.compile(r"^[A-Z0-9\.\-]+_[0-9]{8}T[0-9]{6}Z$")
    iso_ts_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T")

    for offset, raw_row in enumerate(values, start=header_row_idx + 1):
        row = raw_row + [""] * (26 - len(raw_row))
        run_cell = str(row[run_col_idx]).strip()
        start_cell = str(row[start_col_idx]).strip()
        end_cell = str(row[end_col_idx]).strip()

        if run_cell == "" and run_id_pattern.match(start_cell):
            repaired = list(row)
            max_idx = min(25, share_link_col_idx + 1)
            for idx in range(run_col_idx, max_idx):
                repaired[idx] = row[idx + 1]
            updates.append(
                {
                    "range": f"{sheet_name}!A{offset}:Z{offset}",
                    "values": [repaired],
                }
            )
            continue

        if not (iso_ts_pattern.match(run_cell) and run_id_pattern.match(start_cell)):
            continue

        notes = str(row[12]).strip() if len(row) > 12 else ""
        repaired = list(row)
        repaired[run_col_idx] = start_cell
        repaired[start_col_idx] = run_cell
        repaired[end_col_idx] = end_cell if iso_ts_pattern.match(end_cell) else run_cell
        repaired[ticker_col_idx] = str(row[3]).strip() if len(row) > 3 else repaired[ticker_col_idx]
        if company_col_idx is not None:
            repaired[company_col_idx] = ""
        if template_col_idx is not None:
            repaired[template_col_idx] = ""
        if agent_col_idx is not None:
            repaired[agent_col_idx] = ""
        if model_col_idx is not None:
            repaired[model_col_idx] = ""
        status_value = str(row[11]).strip() if len(row) > 11 else ""
        repaired[status_col_idx] = f"{status_value} | {notes}" if notes and status_value else status_value
        repaired[value_col_idx] = row[6] if len(row) > 6 else ""
        repaired[wacc_col_idx] = row[9] if len(row) > 9 else ""
        repaired[g_col_idx] = row[10] if len(row) > 10 else ""
        if tokens_col_idx is not None:
            repaired[tokens_col_idx] = ""
        if cost_col_idx is not None:
            repaired[cost_col_idx] = ""
        repaired[spreadsheet_id_col_idx] = row[4] if len(row) > 4 else ""
        repaired[share_link_col_idx] = row[5] if len(row) > 5 else ""

        updates.append(
            {
                "range": f"{sheet_name}!A{offset}:Z{offset}",
                "values": [repaired],
            }
        )

    if not updates:
        return 0

    (
        sheets.spreadsheets()
        .values()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": updates},
        )
        .execute()
    )
    return len(updates)


def _ensure_sheet_tab_exists(
    sheets: Any, spreadsheet_id: str, sheet_name: str
) -> str:
    meta = (
        sheets.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="properties.title,sheets.properties.title",
        )
        .execute()
    )
    tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if sheet_name in tabs:
        return sheet_name

    (
        sheets.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
        )
        .execute()
    )
    return sheet_name


def run(args: argparse.Namespace) -> dict[str, Any]:
    _load_env_file(Path(args.env_file))

    payload = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    ticker = payload["ticker"].upper()
    sheets_inputs = payload["sheets_inputs"]
    start_ts = datetime.now(timezone.utc).isoformat()
    run_id = f"{ticker}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    credentials = load_credentials()
    drive = build("drive", "v3", credentials=credentials)
    sheets = build("sheets", "v4", credentials=credentials)

    template = _find_drive_file_by_name(drive, args.template_name)
    new_name = _make_run_name(ticker, args.template_name)
    run_sheet = _copy_template(drive, template["id"], new_name)
    run_spreadsheet_id = run_sheet["id"]

    _enable_iterative_calculation(sheets, run_spreadsheet_id)
    _write_named_ranges(sheets, run_spreadsheet_id, sheets_inputs)
    outputs = _poll_outputs(sheets, run_spreadsheet_id, timeout_seconds=args.poll_timeout_seconds)
    issues = _run_guardrails(outputs, sheets_inputs)
    end_ts = datetime.now(timezone.utc).isoformat()
    run_url = run_sheet.get("webViewLink") or f"https://docs.google.com/spreadsheets/d/{run_spreadsheet_id}/edit"

    logbook_append_error = None
    logbook_sheet_used = None
    repaired_rows = 0
    try:
        logbook = _find_drive_file_by_name(drive, args.logbook_name)
        logbook_sheet_used = _ensure_sheet_tab_exists(
            sheets=sheets,
            spreadsheet_id=logbook["id"],
            sheet_name=args.logbook_sheet_name,
        )
        header_row_idx, headers = _find_runs_header_row(
            sheets=sheets,
            spreadsheet_id=logbook["id"],
            sheet_name=logbook_sheet_used,
        )
        repaired_rows = _repair_legacy_misaligned_runs_rows(
            sheets=sheets,
            spreadsheet_id=logbook["id"],
            sheet_name=logbook_sheet_used,
            header_row_idx=header_row_idx,
            headers=headers,
        )
        status = "FAILED" if any(issue.startswith("Hard fail") for issue in issues) else "COMPLETED"
        values_by_header = {
            "runid": run_id,
            "starttsutc": start_ts,
            "endtsutc": end_ts,
            "ticker": ticker,
            "company": sheets_inputs.get("inp_name", ""),
            "templatev": args.template_name,
            "agentv": args.agent_version,
            "model": args.model_name,
            "status": status,
            "valueshare": outputs.get("out_value_per_share"),
            "wacc": outputs.get("out_wacc"),
            "g": outputs.get("out_terminal_g"),
            "tokens": args.tokens,
            "costusd": args.cost_usd,
            "spreadsheetid": run_spreadsheet_id,
            "sharelink": run_url,
        }
        header_start_idx = next(i for i, h in enumerate(headers) if h)
        header_end_idx = max(i for i, h in enumerate(headers) if h)
        append_headers = headers[header_start_idx : header_end_idx + 1]
        _append_logbook_row(
            sheets,
            logbook["id"],
            _build_runs_row_from_headers(append_headers, values_by_header),
            logbook_sheet_used,
            target_columns_range=(
                f"{_a1_col(header_start_idx)}:"
                f"{_a1_col(header_end_idx)}"
            ),
        )
    except Exception as exc:  # pragma: no cover - runtime diagnostic path
        logbook_append_error = str(exc)

    return {
        "ticker": ticker,
        "dataset": args.dataset,
        "run_id": run_id,
        "template_file_id": template["id"],
        "run_spreadsheet_id": run_spreadsheet_id,
        "run_spreadsheet_url": run_url,
        "outputs": outputs,
        "guardrail_issues": issues,
        "logbook_sheet_used": logbook_sheet_used,
        "logbook_repaired_rows": repaired_rows,
        "logbook_append_error": logbook_append_error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy valuation template from Drive, write canonical inputs, and read outputs."
    )
    parser.add_argument(
        "--dataset",
        required=True,
        help="Path to canonical dataset artifact JSON",
    )
    parser.add_argument(
        "--template-name",
        default="Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx",
        help="Template file name in Google Drive",
    )
    parser.add_argument(
        "--logbook-name",
        default="Valuation_Agent_Logbook_ExcelGraph.xlsx",
        help="Logbook file name in Google Drive",
    )
    parser.add_argument(
        "--logbook-sheet-name",
        default="Runs",
        help="Sheet/tab name inside logbook for append",
    )
    parser.add_argument(
        "--poll-timeout-seconds",
        type=int,
        default=90,
        help="How long to poll for out_value_per_share output",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Environment file path to preload (default: .env)",
    )
    parser.add_argument(
        "--agent-version",
        default="us_stocks_valuation_agent_excelgraph_v1",
        help="Agent version string logged to Runs sheet",
    )
    parser.add_argument(
        "--model-name",
        default="DCF_Skill_ExcelGraph_Logbook",
        help="Model label logged to Runs sheet",
    )
    parser.add_argument(
        "--tokens",
        default="",
        help="Optional token usage logged to Runs sheet",
    )
    parser.add_argument(
        "--cost-usd",
        default="",
        help="Optional run cost in USD logged to Runs sheet",
    )
    args = parser.parse_args()

    try:
        result = run(args)
    except Exception as exc:  # pragma: no cover - runtime diagnostic path
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
