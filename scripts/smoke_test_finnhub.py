#!/usr/bin/env python3
"""Smoke test for Finnhub market/news/peer endpoints."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.tools.market.finnhub import FinnhubMarketClient
from backend.app.tools.news.finnhub import FinnhubNewsClient
from backend.app.tools.peer.finnhub import FinnhubPeerUniverseClient
from scripts.smoke_test_common import load_env_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Finnhub smoke test")
    parser.add_argument("--ticker", default="AAPL", help="Ticker to probe")
    parser.add_argument("--env-file", default=".env", help="Env file path")
    args = parser.parse_args()

    load_env_file(args.env_file)
    api_key = os.getenv("FINNHUB_API_KEY", "").strip()
    if not api_key:
        print("FAIL: Missing FINNHUB_API_KEY")
        return 1

    ticker = args.ticker.strip().upper()
    market_client = FinnhubMarketClient(api_key=api_key)
    news_client = FinnhubNewsClient(api_key=api_key)
    peer_client = FinnhubPeerUniverseClient(api_key=api_key)

    try:
        market = market_client.fetch_market_snapshot(ticker)
        news = news_client.fetch_company_news(ticker, limit=3)
        peers = peer_client.discover_peers(ticker, limit=5)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    if market.price is None:
        print("FAIL: Market price returned None")
        return 1

    print("PASS")
    print(f"Ticker: {ticker}")
    print(f"Price: {market.price}")
    print(f"News count: {len(news)}")
    print(f"Peers count: {len(peers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
