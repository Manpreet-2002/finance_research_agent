#!/usr/bin/env python3
"""End-to-end smoke test for deterministic LangGraph valuation runner."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.settings import load_settings
from backend.app.orchestrator.valuation_runner import ValuationRunner
from backend.app.schemas.valuation_run import ValuationRunRequest
from scripts.smoke_test_common import load_env_file


def main() -> int:
    parser = argparse.ArgumentParser(description="LangGraph valuation runner smoke test")
    parser.add_argument("--ticker", default="AAPL", help="Ticker symbol")
    parser.add_argument("--env-file", default=".env", help="Env file path")
    args = parser.parse_args()

    load_env_file(args.env_file)
    settings = load_settings()

    required_env = {
        "GOOGLE_API_KEY": settings.google_api_key,
        "FINNHUB_API_KEY": settings.finnhub_api_key,
        "FRED_API_KEY": settings.fred_api_key,
        "TAVILY_API_KEY": settings.tavily_api_key,
        "ALPHA_VANTAGE_API_KEY": settings.alpha_vantage_api_key,
    }
    missing = [key for key, value in required_env.items() if not str(value).strip()]
    if missing:
        print(f"FAIL: Missing required env vars: {', '.join(missing)}")
        return 1

    if settings.google_auth_mode.strip().lower() != "oauth":
        print("FAIL: GOOGLE_AUTH_MODE must be oauth")
        return 1

    token_path = Path(settings.google_oauth_token_file)
    client_secret_path = Path(settings.google_oauth_client_secret_file)
    if not token_path.exists() and not client_secret_path.exists():
        print(
            "FAIL: Missing Google OAuth credentials. Provide token file or client secret file."
        )
        return 1

    run_id = datetime.now(timezone.utc).strftime("smoke_%Y%m%dT%H%M%SZ")
    request = ValuationRunRequest(
        ticker=args.ticker.strip().upper(),
        run_id=run_id,
        overrides={"log_status": "RUNNING"},
    )

    runner = ValuationRunner(settings=settings)

    try:
        result = runner.run(request)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    print("PASS" if result.status == "COMPLETED" else "FAIL")
    print(f"Run ID: {result.run_id}")
    print(f"Ticker: {request.ticker}")
    print(f"Status: {result.status}")
    print(f"Spreadsheet ID: {result.spreadsheet_id}")
    print(f"Weighted value/share: {result.value_per_share}")
    print(f"Equity value: {result.equity_value}")
    print(f"Enterprise value: {result.enterprise_value}")
    print(f"Phases executed: {', '.join(result.phases_executed)}")
    print(f"Citations summary: {result.citations_summary}")
    print(f"Memo chars: {len(result.memo_markdown)}")

    if result.notes:
        print("Notes:")
        print(result.notes)

    return 0 if result.status == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
