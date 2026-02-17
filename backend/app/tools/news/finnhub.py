"""Finnhub news adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..contracts import DataSourceCitation, NewsItem
from ..http_client import HttpJsonClient
from .client import NewsClient

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def _from_unix_seconds(raw_value: Any) -> datetime | None:
    try:
        if raw_value in (None, ""):
            return None
        return datetime.fromtimestamp(int(raw_value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


@dataclass
class FinnhubNewsClient(NewsClient):
    """Fetches company news from Finnhub."""

    api_key: str
    lookback_days: int = 14
    http_client: HttpJsonClient = field(default_factory=HttpJsonClient)
    _citations: list[DataSourceCitation] = field(default_factory=list, init=False)

    def fetch_company_news(self, ticker: str, limit: int = 10) -> list[NewsItem]:
        if not self.api_key:
            raise RuntimeError("FINNHUB_API_KEY is required for news fetches.")

        today = date.today()
        start = today - timedelta(days=self.lookback_days)
        params = {
            "symbol": ticker,
            "from": start.isoformat(),
            "to": today.isoformat(),
            "token": self.api_key,
        }
        endpoint = "company-news"
        payload = self.http_client.get_json(
            f"{FINNHUB_BASE_URL}/{endpoint}",
            params=params,
        )
        self._citations = [
            DataSourceCitation(
                source="finnhub",
                endpoint=endpoint,
                url=f"{FINNHUB_BASE_URL}/{endpoint}",
                accessed_at_utc=datetime.now(timezone.utc),
                note=f"from={start.isoformat()} to={today.isoformat()}",
            )
        ]

        if not isinstance(payload, list):
            return []

        items: list[NewsItem] = []
        for row in payload[: max(limit, 0)]:
            if not isinstance(row, dict):
                continue
            items.append(
                NewsItem(
                    headline=str(row.get("headline") or ""),
                    publisher=str(row.get("source") or ""),
                    published_at_utc=_from_unix_seconds(row.get("datetime")),
                    url=str(row.get("url") or ""),
                    summary=str(row.get("summary") or ""),
                )
            )
        return items

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        if self._citations:
            return list(self._citations)
        return [
            DataSourceCitation(
                source="finnhub",
                endpoint="company-news",
                url=f"{FINNHUB_BASE_URL}/company-news",
                accessed_at_utc=datetime.now(timezone.utc),
                note=f"Fallback citation for {ticker}; fields=headline,publisher,url.",
            )
        ]
