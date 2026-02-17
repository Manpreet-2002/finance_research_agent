"""Market data interfaces for price, shares, beta, and market cap."""

from __future__ import annotations

from typing import Protocol

from ..contracts import DataSourceCitation, MarketSnapshot


class MarketClient(Protocol):
    """Interface for quote and market-structure data providers."""

    def fetch_market_snapshot(self, ticker: str) -> MarketSnapshot:
        """Fetch current market snapshot for valuation inputs."""

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        """Return source citations for provider endpoints used."""
