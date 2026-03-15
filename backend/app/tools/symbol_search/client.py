"""Shared contracts and ranking helpers for symbol lookup."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

MAX_SYMBOL_SEARCH_RESULTS = 10
_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[A-Z0-9]+")
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


@dataclass(frozen=True)
class SymbolSearchMatch:
    """Normalized search result shown in ticker-picker UI."""

    ticker: str
    company_name: str
    source: str

    @property
    def label(self) -> str:
        return f"{self.ticker} - {self.company_name}"


class SymbolSearchClient(Protocol):
    """Interface for provider-backed symbol search adapters."""

    def search(self, query: str, *, limit: int = MAX_SYMBOL_SEARCH_RESULTS) -> list[SymbolSearchMatch]:
        """Return best matches for a partially entered ticker or company name."""


class SymbolSearchServiceProtocol(Protocol):
    """Interface for app-level symbol search service."""

    def search(self, query: str, *, limit: int = MAX_SYMBOL_SEARCH_RESULTS) -> list[SymbolSearchMatch]:
        """Return merged, ranked symbol matches."""


def clamp_limit(limit: int) -> int:
    """Keep result limits within the UI-supported bounds."""
    return max(1, min(MAX_SYMBOL_SEARCH_RESULTS, int(limit)))


def normalize_query(query: str) -> str:
    """Collapse whitespace without removing signal from the raw query."""
    return _WHITESPACE_RE.sub(" ", str(query or "").strip())


def clean_display_text(value: str) -> str:
    """Normalize display text from external providers."""
    return _WHITESPACE_RE.sub(" ", str(value or "").strip())


def is_supported_ticker(value: str) -> bool:
    """Limit results to tickers accepted by the execution API."""
    return bool(_TICKER_RE.fullmatch(str(value or "").strip().upper()))


def is_match_candidate(result: SymbolSearchMatch, query: str) -> bool:
    """Cheap predicate used by local-directory search clients."""
    normalized_query = normalize_query(query)
    if not normalized_query:
        return False
    query_upper = normalized_query.upper()
    query_lower = normalized_query.lower()
    ticker = result.ticker.upper()
    company_name = result.company_name.lower()
    if ticker == query_upper:
        return True
    if query_upper in ticker:
        return True
    if query_lower in company_name:
        return True
    return any(token.startswith(query_upper) for token in _TOKEN_RE.findall(company_name.upper()))


def rank_matches(
    matches: list[SymbolSearchMatch],
    *,
    query: str,
    limit: int = MAX_SYMBOL_SEARCH_RESULTS,
) -> list[SymbolSearchMatch]:
    """Deduplicate and deterministically rank mixed-provider search results."""
    normalized_query = normalize_query(query)
    if not normalized_query:
        return []

    query_upper = normalized_query.upper()
    query_lower = normalized_query.lower()
    deduped: dict[str, SymbolSearchMatch] = {}
    for match in matches:
        ticker = clean_display_text(match.ticker).upper()
        company_name = clean_display_text(match.company_name)
        if not ticker or not company_name or not is_supported_ticker(ticker):
            continue
        candidate = SymbolSearchMatch(
            ticker=ticker,
            company_name=company_name,
            source=match.source,
        )
        if not is_match_candidate(candidate, normalized_query):
            continue
        current = deduped.get(candidate.ticker)
        if current is None or _rank_key(candidate, query_upper, query_lower) < _rank_key(
            current,
            query_upper,
            query_lower,
        ):
            deduped[candidate.ticker] = candidate

    ranked = sorted(
        deduped.values(),
        key=lambda item: _rank_key(item, query_upper, query_lower),
    )
    return ranked[:clamp_limit(limit)]


def _rank_key(match: SymbolSearchMatch, query_upper: str, query_lower: str) -> tuple[int, int, int, str, str]:
    ticker = match.ticker.upper()
    company_name = clean_display_text(match.company_name)
    company_name_lower = company_name.lower()
    company_tokens = _TOKEN_RE.findall(company_name.upper())

    if ticker == query_upper:
        bucket = 0
    elif company_name_lower == query_lower:
        bucket = 1
    elif ticker.startswith(query_upper):
        bucket = 2
    elif company_name_lower.startswith(query_lower):
        bucket = 3
    elif any(token.startswith(query_upper) for token in company_tokens):
        bucket = 4
    elif query_upper in ticker:
        bucket = 5
    else:
        bucket = 6

    return (
        bucket,
        len(ticker),
        len(company_name),
        ticker,
        company_name_lower,
    )
