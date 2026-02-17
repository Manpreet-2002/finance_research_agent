#!/usr/bin/env python3
"""Smoke test for Tavily web-search integration."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.tools.news.tavily import TavilyNewsClient
from scripts.smoke_test_common import load_env_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Tavily smoke test")
    parser.add_argument("--ticker", default="AAPL", help="Ticker symbol")
    parser.add_argument("--env-file", default=".env", help="Env file path")
    args = parser.parse_args()

    load_env_file(args.env_file)
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        print("FAIL: Missing TAVILY_API_KEY")
        return 1

    client = TavilyNewsClient(api_key=api_key)
    try:
        items = client.fetch_company_news(args.ticker.strip().upper(), limit=5)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    print("PASS")
    print(f"Ticker: {args.ticker.strip().upper()}")
    print(f"Result count: {len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
