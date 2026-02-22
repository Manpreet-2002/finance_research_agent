#!/usr/bin/env python3
"""Force refresh Google OAuth token via browser consent flow.

This script loads env settings, deletes the current OAuth token (if present),
opens a browser for consent, and writes a new token file with Drive+Sheets
scopes used by the valuation agent.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from backend.app.core.settings import load_settings
from scripts.smoke_test_common import load_env_file

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
SCOPES = [SHEETS_SCOPE, DRIVE_SCOPE]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh Google OAuth token via browser consent flow."
    )
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument(
        "--keep-token",
        action="store_true",
        help="Do not delete existing token before opening consent flow.",
    )
    args = parser.parse_args()

    load_env_file(args.env_file)
    settings = load_settings()

    if settings.google_auth_mode.strip().lower() != "oauth":
        print("ERROR: GOOGLE_AUTH_MODE must be 'oauth' to refresh OAuth token.")
        return 1

    client_secret_path = Path(settings.google_oauth_client_secret_file)
    token_path = Path(settings.google_oauth_token_file)

    if not client_secret_path.exists():
        print(
            "ERROR: OAuth client secret file not found: "
            f"{client_secret_path.resolve()}"
        )
        return 1

    if token_path.exists() and not args.keep_token:
        token_path.unlink()
        print(f"Deleted existing token file: {token_path.resolve()}")

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(
        port=0,
        open_browser=True,
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    token_path.write_text(creds.to_json(), encoding="utf-8")

    print("OAuth token refreshed successfully.")
    print(f"Token file: {token_path.resolve()}")
    print(f"Scopes: {', '.join(SCOPES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
