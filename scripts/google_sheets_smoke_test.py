#!/usr/bin/env python3
"""Google Sheets API smoke test for formula execution.

Creates a spreadsheet named test_graph_1, writes 1..10 into A1:A10,
writes =SUM(A1:A10) into A11, then reads A11 to verify computed value.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _load_credentials():
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    cred_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if cred_path:
        return service_account.Credentials.from_service_account_file(
            cred_path, scopes=SCOPES
        )

    if cred_json:
        info = json.loads(cred_json)
        return service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )

    oauth_client_file = Path(
        os.getenv("GOOGLE_OAUTH_CLIENT_SECRET_FILE", "credentials.json")
    )
    token_file = Path(os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "token.json"))

    creds: UserCredentials | None = None
    if token_file.exists():
        creds = UserCredentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not oauth_client_file.exists():
                raise RuntimeError(
                    "Missing credentials. Provide service-account credentials via "
                    "GOOGLE_APPLICATION_CREDENTIALS/GOOGLE_SERVICE_ACCOUNT_JSON, or "
                    "provide OAuth client secrets at credentials.json."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(oauth_client_file), SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return creds


def run_smoke_test(title: str) -> dict[str, Any]:
    credentials = _load_credentials()
    service = build("sheets", "v4", credentials=credentials)

    create_resp = (
        service.spreadsheets()
        .create(body={"properties": {"title": title}}, fields="spreadsheetId,spreadsheetUrl")
        .execute()
    )
    spreadsheet_id = create_resp["spreadsheetId"]
    spreadsheet_url = create_resp["spreadsheetUrl"]

    values = [[i] for i in range(1, 11)] + [["=SUM(A1:A10)"]]
    (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range="A1:A11",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        )
        .execute()
    )

    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range="A11",
            valueRenderOption="UNFORMATTED_VALUE",
        )
        .execute()
    )

    a11 = result.get("values", [[None]])[0][0]
    if a11 != 55:
        raise RuntimeError(f"Smoke test failed: expected A11=55, got {a11!r}")

    return {
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_url": spreadsheet_url,
        "a11_value": a11,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Google Sheets API smoke test")
    parser.add_argument("--title", default="test_graph_1", help="Spreadsheet title")
    args = parser.parse_args()

    try:
        output = run_smoke_test(args.title)
    except Exception as exc:  # pragma: no cover - runtime diagnostic path
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Smoke test passed.")
    print(f"Spreadsheet ID: {output['spreadsheet_id']}")
    print(f"Spreadsheet URL: {output['spreadsheet_url']}")
    print(f"A11: {output['a11_value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
