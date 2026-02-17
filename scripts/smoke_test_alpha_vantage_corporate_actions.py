#!/usr/bin/env python3
"""Smoke test for Alpha Vantage corporate-actions integration."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.tools.corporate_actions.alpha_vantage import (
    AlphaVantageCorporateActionsClient,
)
from scripts.smoke_test_common import load_env_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Alpha Vantage corporate-actions smoke test"
    )
    parser.add_argument("--ticker", default="AAPL", help="Ticker symbol")
    parser.add_argument("--env-file", default=".env", help="Env file path")
    args = parser.parse_args()

    load_env_file(args.env_file)
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
    if not api_key:
        print("FAIL: Missing ALPHA_VANTAGE_API_KEY")
        return 1

    client = AlphaVantageCorporateActionsClient(api_key=api_key)
    try:
        actions = client.fetch_corporate_actions(args.ticker.strip().upper(), limit=20)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    print("PASS")
    print(f"Ticker: {args.ticker.strip().upper()}")
    print(f"Actions fetched: {len(actions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
