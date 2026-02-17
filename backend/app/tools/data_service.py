"""Unified data-service entrypoint for canonical valuation datasets."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from time import perf_counter
from typing import Any

from .contracts import CanonicalValuationDataset
from .fundamentals.client import FundamentalsClient
from .market.client import MarketClient
from .news.client import NewsClient
from .rates.client import RatesClient


@dataclass
class DataService:
    """Coordinates source clients and returns normalized run inputs."""

    fundamentals_client: FundamentalsClient
    market_client: MarketClient
    rates_client: RatesClient
    news_client: NewsClient
    default_assumptions: dict[str, Any] = field(default_factory=dict)
    _logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("finance_research_agent.tools.data_service"),
        init=False,
        repr=False,
    )

    def build_canonical_dataset(self, ticker: str) -> CanonicalValuationDataset:
        """Fetch and normalize the full dataset needed for a DCF run."""
        started = perf_counter()
        self._logger.info("canonical_dataset_start ticker=%s", ticker)
        fundamentals = self.fundamentals_client.fetch_company_fundamentals(ticker)
        market = self.market_client.fetch_market_snapshot(ticker)
        rates = self.rates_client.fetch_rates_snapshot()
        news = self._safe_list_call(
            lambda: self.news_client.fetch_company_news(ticker),
            context="news.fetch_company_news",
        )

        citations = []
        citations.extend(
            self._safe_list_call(
                lambda: self.fundamentals_client.fetch_citations(ticker),
                context="fundamentals.fetch_citations",
            )
        )
        citations.extend(
            self._safe_list_call(
                lambda: self.market_client.fetch_citations(ticker),
                context="market.fetch_citations",
            )
        )
        citations.extend(
            self._safe_list_call(
                lambda: self.rates_client.fetch_citations(),
                context="rates.fetch_citations",
            )
        )
        citations.extend(
            self._safe_list_call(
                lambda: self.news_client.fetch_citations(ticker),
                context="news.fetch_citations",
            )
        )

        dataset = CanonicalValuationDataset(
            ticker=ticker,
            fundamentals=fundamentals,
            market=market,
            rates=rates,
            news=news,
            citations=citations,
            assumptions=dict(self.default_assumptions),
            tsm=CanonicalValuationDataset.derive_tsm_snapshot(
                fundamentals=fundamentals,
                market=market,
            ),
        )
        elapsed_ms = (perf_counter() - started) * 1000.0
        self._logger.info(
            "canonical_dataset_end ticker=%s news_items=%s citations=%s elapsed_ms=%.2f",
            ticker,
            len(dataset.news),
            len(dataset.citations),
            elapsed_ms,
        )
        return dataset

    def _safe_list_call(self, fn: Any, *, context: str) -> list[Any]:
        try:
            value = fn()
        except Exception as exc:
            self._logger.warning(
                "canonical_provider_degraded ticker_context=%s error=%s",
                context,
                exc,
            )
            return []
        if isinstance(value, list):
            return value
        return []
