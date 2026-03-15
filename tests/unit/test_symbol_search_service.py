"""Unit tests for symbol search service behavior."""

from __future__ import annotations

from backend.app.tools.symbol_search.client import SymbolSearchMatch
from backend.app.tools.symbol_search.service import SymbolSearchService


class FakeSearchClient:
    def __init__(
        self,
        matches: list[SymbolSearchMatch] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._matches = matches or []
        self._error = error

    def search(self, query: str, *, limit: int = 10) -> list[SymbolSearchMatch]:
        if self._error is not None:
            raise self._error
        return list(self._matches)[:limit]


def test_symbol_search_service_ranks_exact_ticker_prefix_and_name_matches() -> None:
    service = SymbolSearchService(
        primary_client=FakeSearchClient(
            matches=[
                SymbolSearchMatch(
                    ticker="APP",
                    company_name="AppLovin Corporation",
                    source="finnhub",
                ),
                SymbolSearchMatch(
                    ticker="APPN",
                    company_name="Appian Corporation",
                    source="finnhub",
                ),
                SymbolSearchMatch(
                    ticker="AAPL",
                    company_name="Apple Inc.",
                    source="finnhub",
                ),
            ]
        ),
        fallback_client=FakeSearchClient(
            matches=[
                SymbolSearchMatch(
                    ticker="APP",
                    company_name="AppLovin Corporation",
                    source="sec",
                ),
                SymbolSearchMatch(
                    ticker="APPF",
                    company_name="AppFolio, Inc.",
                    source="sec",
                ),
            ]
        ),
    )

    results = service.search("app")

    assert [row.ticker for row in results] == ["APP", "APPF", "APPN", "AAPL"]
    assert results[0].label == "APP - AppLovin Corporation"


def test_symbol_search_service_uses_fallback_when_primary_fails() -> None:
    service = SymbolSearchService(
        primary_client=FakeSearchClient(error=RuntimeError("finnhub unavailable")),
        fallback_client=FakeSearchClient(
            matches=[
                SymbolSearchMatch(
                    ticker="MSFT",
                    company_name="Microsoft Corporation",
                    source="sec",
                )
            ]
        ),
    )

    results = service.search("microsoft")

    assert len(results) == 1
    assert results[0].ticker == "MSFT"
    assert results[0].label == "MSFT - Microsoft Corporation"


def test_symbol_search_service_caps_results_to_ten() -> None:
    matches = [
        SymbolSearchMatch(
            ticker=f"AA{i}",
            company_name=f"Alpha {i}",
            source="sec",
        )
        for i in range(12)
    ]
    service = SymbolSearchService(primary_client=FakeSearchClient(matches=matches))

    results = service.search("aa", limit=25)

    assert len(results) == 10


def test_symbol_search_service_raises_when_all_providers_fail() -> None:
    service = SymbolSearchService(
        primary_client=FakeSearchClient(error=RuntimeError("primary down")),
        fallback_client=FakeSearchClient(error=RuntimeError("fallback down")),
    )

    try:
        service.search("apple")
    except RuntimeError as exc:
        assert "Symbol search failed" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("Expected search failure when all providers fail.")
