#!/usr/bin/env python3
"""Build and save canonical valuation dataset artifacts for a ticker."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.settings import load_settings
from backend.app.tools.market.finnhub import FinnhubMarketClient
from backend.app.tools.provider_factory import build_data_service
from backend.app.tools.rates.fred import FredRatesClient
from backend.app.tools.contracts import REQUIRED_DCF_INPUT_RANGES


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


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {k: _to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


def _run_checks(ticker: str, settings: Any) -> dict[str, Any]:
    checks: dict[str, Any] = {}

    try:
        market_client = FinnhubMarketClient(api_key=settings.finnhub_api_key)
        snapshot = market_client.fetch_market_snapshot(ticker)
        checks["finnhub"] = {
            "ok": True,
            "price": snapshot.price,
            "captured_at_utc": snapshot.captured_at_utc.isoformat(),
        }
    except Exception as exc:  # pragma: no cover - runtime diagnostics
        checks["finnhub"] = {"ok": False, "error": str(exc)}

    try:
        rates_client = FredRatesClient(
            api_key=settings.fred_api_key,
            rf_series_id=settings.fred_rf_series_id,
            default_equity_risk_premium=settings.default_equity_risk_premium,
            default_cost_of_debt=settings.default_cost_of_debt,
            default_debt_weight=settings.default_debt_weight,
        )
        snapshot = rates_client.fetch_rates_snapshot()
        checks["fred"] = {
            "ok": True,
            "risk_free_rate": snapshot.risk_free_rate,
            "captured_at_utc": snapshot.captured_at_utc.isoformat(),
        }
    except Exception as exc:  # pragma: no cover - runtime diagnostics
        checks["fred"] = {"ok": False, "error": str(exc)}

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build canonical dataset and validate Finnhub/FRED keys."
    )
    parser.add_argument("--ticker", default="GOOG", help="Ticker symbol to fetch")
    parser.add_argument(
        "--outdir",
        default="artifacts/canonical_datasets",
        help="Output directory for dataset artifact JSON",
    )
    parser.add_argument(
        "--env-file", default=".env", help="Environment file path (default: .env)"
    )
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))

    # Ensure this run checks Finnhub + FRED explicitly.
    os.environ["FUNDAMENTALS_PROVIDER"] = "finnhub"
    os.environ["MARKET_DATA_PROVIDER"] = "finnhub"
    os.environ["NEWS_PROVIDER"] = "finnhub"
    os.environ["RATES_PROVIDER"] = "fred"

    settings = load_settings()

    if not settings.finnhub_api_key:
        raise RuntimeError("Missing FINNHUB_API_KEY in environment.")
    if not settings.fred_api_key:
        raise RuntimeError("Missing FRED_API_KEY in environment.")

    service = build_data_service(settings)
    dataset = service.build_canonical_dataset(args.ticker)
    sheets_inputs = dataset.to_sheets_named_ranges()
    missing_ranges = [name for name in REQUIRED_DCF_INPUT_RANGES if name not in sheets_inputs]
    null_ranges = [name for name in REQUIRED_DCF_INPUT_RANGES if sheets_inputs.get(name) is None]

    checks = _run_checks(args.ticker, settings)

    output_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ticker": args.ticker,
        "provider_selection": {
            "fundamentals_provider": settings.fundamentals_provider,
            "market_data_provider": settings.market_data_provider,
            "news_provider": settings.news_provider,
            "rates_provider": settings.rates_provider,
        },
        "api_key_presence": {
            "finnhub_api_key_present": bool(settings.finnhub_api_key),
            "fred_api_key_present": bool(settings.fred_api_key),
        },
        "api_checks": checks,
        "canonical_dataset": _to_jsonable(dataset),
        "sheets_inputs": _to_jsonable(sheets_inputs),
        "sheets_input_completeness": {
            "required_count": len(REQUIRED_DCF_INPUT_RANGES),
            "missing_ranges": missing_ranges,
            "null_ranges": null_ranges,
            "is_complete": not missing_ranges and not null_ranges,
        },
    }

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outfile = outdir / f"{args.ticker.upper()}_canonical_dataset_{ts}.json"
    outfile.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    print("Canonical dataset saved.")
    print(f"File: {outfile}")
    print(f"Finnhub check ok: {output_payload['api_checks']['finnhub']['ok']}")
    print(f"FRED check ok: {output_payload['api_checks']['fred']['ok']}")
    print(
        "Sheets input completeness: "
        f"{output_payload['sheets_input_completeness']['is_complete']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
