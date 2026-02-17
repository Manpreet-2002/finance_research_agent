"""Tavily web-search adapter for catalyst and risk evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from ..contracts import DataSourceCitation, NewsItem
from ..http_client import HttpJsonClient
from .client import NewsClient

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _parse_datetime(raw_value: Any) -> datetime | None:
    if raw_value in (None, ""):
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _publisher_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().strip()
    except Exception:  # pragma: no cover - defensive fallback
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


@dataclass
class TavilyNewsClient(NewsClient):
    """Fetches open-web evidence from Tavily search."""

    api_key: str
    include_domains: tuple[str, ...] = ()
    http_client: HttpJsonClient = field(default_factory=HttpJsonClient)
    _citations: list[DataSourceCitation] = field(default_factory=list, init=False)

    def fetch_company_news(self, ticker: str, limit: int = 10) -> list[NewsItem]:
        if not self.api_key:
            raise RuntimeError("TAVILY_API_KEY is required for Tavily searches.")

        max_results = max(1, min(limit, 20))
        query = (
            f"{ticker} stock catalysts risks earnings guidance competitive landscape"
        )
        payload: dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "include_answer": False,
            "include_images": False,
        }
        if self.include_domains:
            payload["include_domains"] = list(self.include_domains)

        response = self.http_client.post_json(TAVILY_SEARCH_URL, payload=payload)
        self._citations = [
            DataSourceCitation(
                source="tavily",
                endpoint="search",
                url=TAVILY_SEARCH_URL,
                accessed_at_utc=datetime.now(timezone.utc),
                note=f"query={query}",
            )
        ]
        if not isinstance(response, dict):
            return []
        rows = response.get("results")
        if not isinstance(rows, list):
            return []

        items: list[NewsItem] = []
        for row in rows[:max_results]:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "")
            items.append(
                NewsItem(
                    headline=str(row.get("title") or ""),
                    publisher=_publisher_from_url(url),
                    published_at_utc=_parse_datetime(
                        row.get("published_date")
                        or row.get("publishedAt")
                        or row.get("date")
                    ),
                    url=url,
                    summary=str(row.get("content") or ""),
                )
            )
        return items

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        if self._citations:
            return list(self._citations)
        return [
            DataSourceCitation(
                source="tavily",
                endpoint="search",
                url=TAVILY_SEARCH_URL,
                accessed_at_utc=datetime.now(timezone.utc),
                note=f"Fallback Tavily citation for {ticker}.",
            )
        ]
