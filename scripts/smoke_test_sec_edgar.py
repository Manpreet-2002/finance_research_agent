#!/usr/bin/env python3
"""Smoke test for SEC EDGAR/XBRL fundamentals adapter."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.tools.fundamentals.client import SecEdgarFundamentalsClient
from scripts.smoke_test_common import load_env_file


def main() -> int:
    parser = argparse.ArgumentParser(description="SEC EDGAR smoke test")
    parser.add_argument("--ticker", default="AAPL", help="Ticker symbol")
    parser.add_argument("--env-file", default=".env", help="Env file path")
    args = parser.parse_args()

    load_env_file(args.env_file)
    user_agent = os.getenv("SEC_API_USER_AGENT", "").strip()
    contact_email = os.getenv("SEC_CONTACT_EMAIL", "").strip()
    if not user_agent:
        print("FAIL: Missing SEC_API_USER_AGENT")
        return 1

    client = SecEdgarFundamentalsClient(
        user_agent=user_agent,
        contact_email=contact_email,
    )
    try:
        fundamentals = client.fetch_company_fundamentals(args.ticker.strip().upper())
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    print("PASS")
    print(f"Ticker: {args.ticker.strip().upper()}")
    print(f"Company: {fundamentals.company_name}")
    print(f"Revenue TTM/FY proxy: {fundamentals.revenue_ttm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
