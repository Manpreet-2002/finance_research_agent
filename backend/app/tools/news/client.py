"""News interfaces for catalysts and risk headlines."""

from __future__ import annotations

from typing import Protocol

from ..contracts import DataSourceCitation, NewsItem


class NewsClient(Protocol):
    """Interface for market/news provider retrieval."""

    def fetch_company_news(self, ticker: str, limit: int = 10) -> list[NewsItem]:
        """Fetch recent company and market-context headlines."""

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        """Return source citations for the news fetch."""
