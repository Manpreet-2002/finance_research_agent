"""Provider factory unit tests."""

from __future__ import annotations

import pytest

from backend.app.core.settings import Settings
from backend.app.tools.provider_factory import (
    ProviderConfigError,
    build_data_service,
    build_research_service,
)


def test_build_data_service_with_finnhub_and_fred() -> None:
    settings = Settings(
        finnhub_api_key="test-finnhub",
        fred_api_key="test-fred",
        fundamentals_provider="finnhub",
        market_data_provider="finnhub",
        news_provider="finnhub",
        rates_provider="fred",
    )

    service = build_data_service(settings)

    assert service.fundamentals_client.__class__.__name__ == "FinnhubFundamentalsClient"
    assert service.market_client.__class__.__name__ == "FinnhubMarketClient"
    assert service.news_client.__class__.__name__ == "FinnhubNewsClient"
    assert service.rates_client.__class__.__name__ == "FredRatesClient"


def test_build_data_service_rejects_non_v1_provider_names() -> None:
    settings = Settings(
        finnhub_api_key="test-finnhub",
        rates_provider="static",
    )

    with pytest.raises(ProviderConfigError, match="Unsupported RATES_PROVIDER"):
        build_data_service(settings)


def test_build_research_service_with_phase_v1_defaults() -> None:
    settings = Settings(
        finnhub_api_key="test-finnhub",
        alpha_vantage_api_key="test-alpha",
        tavily_api_key="test-tavily",
        news_provider="tavily",
        web_search_provider="tavily",
        transcript_provider="alpha_vantage",
        corporate_actions_provider="alpha_vantage",
        peer_provider="finnhub",
        contradiction_checker_provider="rule_based",
    )

    service = build_research_service(settings)

    assert service.news_client.__class__.__name__ == "TavilyNewsClient"
    assert service.transcript_client.__class__.__name__ == "AlphaVantageTranscriptClient"
    assert (
        service.corporate_actions_client.__class__.__name__
        == "AlphaVantageCorporateActionsClient"
    )
    assert service.peer_client.__class__.__name__ == "FinnhubPeerUniverseClient"
    assert service.contradiction_checker.__class__.__name__ == "RuleBasedContradictionChecker"
