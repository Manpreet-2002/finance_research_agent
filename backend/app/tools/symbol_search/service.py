"""Service that merges provider-backed symbol lookup results."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

from .client import (
    MAX_SYMBOL_SEARCH_RESULTS,
    SymbolSearchClient,
    SymbolSearchMatch,
    clamp_limit,
    normalize_query,
    rank_matches,
)


@dataclass
class SymbolSearchService:
    """App-level symbol search that merges live and fallback sources."""

    primary_client: SymbolSearchClient
    fallback_client: SymbolSearchClient | None = None
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("finance_research_agent.symbol_search")
    )

    def search(self, query: str, *, limit: int = MAX_SYMBOL_SEARCH_RESULTS) -> list[SymbolSearchMatch]:
        normalized_query = normalize_query(query)
        if not normalized_query:
            return []

        clamped_limit = clamp_limit(limit)
        matches: list[SymbolSearchMatch] = []
        errors: list[Exception] = []

        for client_name, client in self._clients():
            try:
                matches.extend(client.search(normalized_query, limit=clamped_limit))
            except Exception as exc:
                errors.append(exc)
                self.logger.warning(
                    "symbol_search_client_failed client=%s query=%s error=%s",
                    client_name,
                    normalized_query,
                    exc,
                )

        ranked = rank_matches(matches, query=normalized_query, limit=clamped_limit)
        if ranked or not errors:
            return ranked
        raise RuntimeError(f"Symbol search failed for query '{normalized_query}': {errors[0]}")

    def _clients(self) -> list[tuple[str, SymbolSearchClient]]:
        clients: list[tuple[str, SymbolSearchClient]] = [("primary", self.primary_client)]
        if self.fallback_client is not None:
            clients.append(("fallback", self.fallback_client))
        return clients
