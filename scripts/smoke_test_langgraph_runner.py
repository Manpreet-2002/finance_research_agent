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
from backend.app.memo.post_run_memo import PostRunMemoService
from backend.app.orchestrator.valuation_runner import ValuationRunner
from backend.app.schemas.valuation_run import ValuationRunRequest
from scripts.smoke_test_common import load_env_file


def main() -> int:
    parser = argparse.ArgumentParser(description="LangGraph valuation runner smoke test")
    parser.add_argument("--ticker", default="AAPL", help="Ticker symbol")
    parser.add_argument("--env-file", default=".env", help="Env file path")
    parser.add_argument(
        "--with-memo",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate local post-run investment memo (default: true). Use --no-with-memo to skip.",
    )
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

    if (
        runner.llm_client is None
        or runner.sheets_engine is None
        or runner.data_service is None
        or runner.research_service is None
    ):
        print("FAIL: Runner dependencies missing for post-run memo stage.")
        return 1

    memo_service = PostRunMemoService(
        settings=settings,
        llm_client=runner.llm_client,
        sheets_engine=runner.sheets_engine,
        data_service=runner.data_service,
        research_service=runner.research_service,
    )
    memo_result = memo_service.generate(
        request=request,
        result=result,
        with_memo=bool(args.with_memo),
    )

    memo_ok = (
        memo_result.status == "COMPLETED"
        if args.with_memo
        else memo_result.status in {"COMPLETED", "SKIPPED"}
    )
    run_ok = result.status == "COMPLETED"
    print("PASS" if run_ok and memo_ok else "FAIL")
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
    print(f"With memo: {args.with_memo}")
    print(f"Wrapper status: {memo_result.status}")
    print(f"Memo manifest: {memo_result.manifest_path}")
    if memo_result.pdf_path:
        print(f"Memo PDF: {memo_result.pdf_path}")
    if memo_result.html_path:
        print(f"Memo HTML: {memo_result.html_path}")
    if memo_result.chart_manifest_path:
        print(f"Charts manifest: {memo_result.chart_manifest_path}")

    if result.notes:
        print("Notes:")
        print(result.notes)
    if memo_result.notes:
        print("Memo notes:")
        for note in memo_result.notes:
            print(f"- {note}")

    return 0 if run_ok and memo_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
