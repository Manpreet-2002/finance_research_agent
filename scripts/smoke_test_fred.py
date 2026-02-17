#!/usr/bin/env python3
"""Smoke test for FRED rates endpoint."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.tools.rates.fred import FredRatesClient
from scripts.smoke_test_common import load_env_file


def main() -> int:
    parser = argparse.ArgumentParser(description="FRED smoke test")
    parser.add_argument("--series-id", default="DGS10", help="FRED series id")
    parser.add_argument("--env-file", default=".env", help="Env file path")
    args = parser.parse_args()

    load_env_file(args.env_file)
    api_key = os.getenv("FRED_API_KEY", "").strip()
    if not api_key:
        print("FAIL: Missing FRED_API_KEY")
        return 1

    client = FredRatesClient(api_key=api_key, rf_series_id=args.series_id)
    try:
        snapshot = client.fetch_rates_snapshot()
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    if snapshot.risk_free_rate is None:
        print("FAIL: risk_free_rate returned None")
        return 1

    print("PASS")
    print(f"Series: {args.series_id}")
    print(f"Risk free rate: {snapshot.risk_free_rate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
