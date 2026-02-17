"""Finnhub market snapshot adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..contracts import DataSourceCitation, MarketSnapshot
from ..http_client import HttpJsonClient
from .client import MarketClient

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def _as_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class FinnhubMarketClient(MarketClient):
    """Fetches price and market-structure inputs from Finnhub."""

    api_key: str
    http_client: HttpJsonClient = field(default_factory=HttpJsonClient)
    _citations: list[DataSourceCitation] = field(default_factory=list, init=False)

    def fetch_market_snapshot(self, ticker: str) -> MarketSnapshot:
        if not self.api_key:
            raise RuntimeError("FINNHUB_API_KEY is required for market data fetches.")

        self._citations = []
        quote = self._request("quote", {"symbol": ticker})
        profile = self._request("stock/profile2", {"symbol": ticker})
        metric = self._request("stock/metric", {"symbol": ticker, "metric": "all"})

        metric_values = metric.get("metric") if isinstance(metric, dict) else {}
        profile_values = profile if isinstance(profile, dict) else {}
        quote_values = quote if isinstance(quote, dict) else {}

        return MarketSnapshot(
            ticker=ticker,
            price=_as_float(quote_values.get("c")),
            beta=_as_float(metric_values.get("beta")),
            market_cap=_as_float(profile_values.get("marketCapitalization")),
            shares_outstanding=_as_float(profile_values.get("shareOutstanding"))
            or _as_float(metric_values.get("shareOutstanding"))
            or _as_float(metric_values.get("sharesOutstanding")),
            captured_at_utc=datetime.now(timezone.utc),
        )

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        if self._citations:
            return list(self._citations)
        now = datetime.now(timezone.utc)
        return [
            DataSourceCitation(
                source="finnhub",
                endpoint="quote",
                url=f"{FINNHUB_BASE_URL}/quote",
                accessed_at_utc=now,
                note=f"Fallback citation for {ticker}; units=USD, beta, shares(mm).",
            )
        ]

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any] | list[Any]:
        query = dict(params)
        query["token"] = self.api_key
        data = self.http_client.get_json(f"{FINNHUB_BASE_URL}/{endpoint}", params=query)
        self._citations.append(
            DataSourceCitation(
                source="finnhub",
                endpoint=endpoint,
                url=f"{FINNHUB_BASE_URL}/{endpoint}",
                accessed_at_utc=datetime.now(timezone.utc),
                note=f"ticker={params.get('symbol', '')}",
            )
        )
        if isinstance(data, dict):
            return data
        return {}
