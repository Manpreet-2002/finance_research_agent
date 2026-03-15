"""SEC ticker-directory fallback for symbol lookup."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..http_client import HttpJsonClient
from ..sec.client import SEC_TICKER_MAP_URL
from .client import (
    MAX_SYMBOL_SEARCH_RESULTS,
    SymbolSearchMatch,
    clean_display_text,
    is_match_candidate,
    is_supported_ticker,
    rank_matches,
)


@dataclass
class SecTickerDirectorySearchClient:
    """Searches the SEC company directory when live-provider results are missing."""

    user_agent: str
    contact_email: str = ""
    http_client: HttpJsonClient = field(default_factory=HttpJsonClient)
    _directory_cache: tuple[SymbolSearchMatch, ...] | None = field(default=None, init=False)

    def search(self, query: str, *, limit: int = MAX_SYMBOL_SEARCH_RESULTS) -> list[SymbolSearchMatch]:
        directory = self._load_directory()
        matches = [row for row in directory if is_match_candidate(row, query)]
        return rank_matches(matches, query=query, limit=limit)

    def _load_directory(self) -> tuple[SymbolSearchMatch, ...]:
        if self._directory_cache is not None:
            return self._directory_cache

        payload = self.http_client.get_json(
            SEC_TICKER_MAP_URL,
            headers=self._sec_headers(),
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected SEC ticker directory response shape.")

        matches: list[SymbolSearchMatch] = []
        for row in payload.values():
            if not isinstance(row, dict):
                continue
            ticker = clean_display_text(str(row.get("ticker", ""))).upper()
            company_name = clean_display_text(str(row.get("title", "")))
            if not is_supported_ticker(ticker) or not company_name:
                continue
            matches.append(
                SymbolSearchMatch(
                    ticker=ticker,
                    company_name=company_name,
                    source="sec",
                )
            )
        self._directory_cache = tuple(matches)
        return self._directory_cache

    def _sec_headers(self) -> dict[str, str]:
        user_agent = self.user_agent.strip() or "finance-research-agent/0.1"
        headers = {"User-Agent": user_agent}
        if self.contact_email.strip():
            headers["From"] = self.contact_email.strip()
        return headers
