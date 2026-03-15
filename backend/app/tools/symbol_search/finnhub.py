"""Finnhub-backed symbol lookup."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..http_client import HttpJsonClient
from .client import (
    MAX_SYMBOL_SEARCH_RESULTS,
    SymbolSearchMatch,
    clean_display_text,
    is_supported_ticker,
    rank_matches,
)

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
_BANNED_TYPE_TOKENS = (
    "bond",
    "crypto",
    "etf",
    "etn",
    "fund",
    "forex",
    "index",
    "mutual",
    "preferred",
    "right",
    "unit",
    "warrant",
)
_BANNED_DESCRIPTION_TOKENS = (
    " etf",
    " etn",
    " fund",
    " right",
    " unit",
    " warrant",
)


@dataclass
class FinnhubSymbolSearchClient:
    """Queries Finnhub symbol lookup for live autocomplete results."""

    api_key: str
    http_client: HttpJsonClient = field(default_factory=HttpJsonClient)

    def search(self, query: str, *, limit: int = MAX_SYMBOL_SEARCH_RESULTS) -> list[SymbolSearchMatch]:
        if not self.api_key.strip():
            return []

        payload = self.http_client.get_json(
            f"{FINNHUB_BASE_URL}/search",
            params={
                "q": query,
                "exchange": "US",
                "token": self.api_key,
            },
        )
        if not isinstance(payload, dict):
            return []

        raw_results = payload.get("result")
        if not isinstance(raw_results, list):
            return []

        matches: list[SymbolSearchMatch] = []
        for row in raw_results:
            if not isinstance(row, dict):
                continue
            match = self._to_match(row)
            if match is None:
                continue
            matches.append(match)
        return rank_matches(matches, query=query, limit=limit)

    def _to_match(self, row: dict[str, Any]) -> SymbolSearchMatch | None:
        raw_type = clean_display_text(str(row.get("type", ""))).lower()
        description = clean_display_text(str(row.get("description", "")))
        description_lower = description.lower()
        if any(token in raw_type for token in _BANNED_TYPE_TOKENS):
            return None
        if any(token in description_lower for token in _BANNED_DESCRIPTION_TOKENS):
            return None

        raw_ticker_values = (
            clean_display_text(str(row.get("displaySymbol", ""))),
            clean_display_text(str(row.get("symbol", ""))),
        )
        ticker = next((item.upper() for item in raw_ticker_values if is_supported_ticker(item)), "")
        if not ticker or not description:
            return None
        return SymbolSearchMatch(
            ticker=ticker,
            company_name=description,
            source="finnhub",
        )
