"""Factory wiring for swappable data and research providers."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.settings import Settings
from .contradiction_checker.client import RuleBasedContradictionChecker
from .corporate_actions.alpha_vantage import AlphaVantageCorporateActionsClient
from .data_service import DataService
from .fundamentals.client import SecEdgarFundamentalsClient
from .fundamentals.finnhub import FinnhubFundamentalsClient
from .market.finnhub import FinnhubMarketClient
from .news.finnhub import FinnhubNewsClient
from .news.tavily import TavilyNewsClient
from .peer.finnhub import FinnhubPeerUniverseClient
from .rates.fred import FredRatesClient
from .research_service import ResearchService
from .transcripts.alpha_vantage import AlphaVantageTranscriptClient


class ProviderConfigError(ValueError):
    """Raised when provider config has unsupported values."""


@dataclass(frozen=True)
class ProviderSelection:
    """Resolved provider names for canonical-data collection."""

    fundamentals_provider: str
    market_data_provider: str
    news_provider: str
    rates_provider: str


@dataclass(frozen=True)
class ResearchProviderSelection:
    """Resolved provider names for extended research tooling."""

    news_provider: str
    transcript_provider: str
    corporate_actions_provider: str
    peer_provider: str
    contradiction_checker_provider: str


def resolve_provider_selection(settings: Settings) -> ProviderSelection:
    """Normalize and return selected provider names for canonical data."""
    return ProviderSelection(
        fundamentals_provider=settings.fundamentals_provider.strip().lower(),
        market_data_provider=settings.market_data_provider.strip().lower(),
        news_provider=settings.news_provider.strip().lower(),
        rates_provider=settings.rates_provider.strip().lower(),
    )


def resolve_research_provider_selection(settings: Settings) -> ResearchProviderSelection:
    """Normalize and return selected provider names for extended tools."""
    news_provider = settings.web_search_provider.strip().lower()
    if not news_provider:
        news_provider = settings.news_provider.strip().lower()
    return ResearchProviderSelection(
        news_provider=news_provider,
        transcript_provider=settings.transcript_provider.strip().lower(),
        corporate_actions_provider=settings.corporate_actions_provider.strip().lower(),
        peer_provider=settings.peer_provider.strip().lower(),
        contradiction_checker_provider=settings.contradiction_checker_provider.strip().lower(),
    )


def _build_fundamentals_client(settings: Settings, provider: str):
    if provider == "finnhub":
        return FinnhubFundamentalsClient(api_key=settings.finnhub_api_key)
    if provider == "sec_edgar":
        return SecEdgarFundamentalsClient(
            user_agent=settings.sec_api_user_agent,
            contact_email=settings.sec_contact_email,
        )
    raise ProviderConfigError(f"Unsupported FUNDAMENTALS_PROVIDER: {provider}")


def _build_market_client(settings: Settings, provider: str):
    if provider == "finnhub":
        return FinnhubMarketClient(api_key=settings.finnhub_api_key)
    raise ProviderConfigError(f"Unsupported MARKET_DATA_PROVIDER: {provider}")


def _build_news_client(settings: Settings, provider: str):
    if provider == "finnhub":
        return FinnhubNewsClient(
            api_key=settings.finnhub_api_key,
            lookback_days=settings.news_lookback_days,
        )
    if provider == "tavily":
        return TavilyNewsClient(api_key=settings.tavily_api_key)
    raise ProviderConfigError(f"Unsupported NEWS_PROVIDER: {provider}")


def _build_rates_client(settings: Settings, provider: str):
    if provider == "fred":
        return FredRatesClient(
            api_key=settings.fred_api_key,
            rf_series_id=settings.fred_rf_series_id,
            default_equity_risk_premium=settings.default_equity_risk_premium,
            default_cost_of_debt=settings.default_cost_of_debt,
            default_debt_weight=settings.default_debt_weight,
        )
    raise ProviderConfigError(f"Unsupported RATES_PROVIDER: {provider}")


def _build_transcript_client(settings: Settings, provider: str):
    if provider == "alpha_vantage":
        return AlphaVantageTranscriptClient(api_key=settings.alpha_vantage_api_key)
    raise ProviderConfigError(f"Unsupported TRANSCRIPT_PROVIDER: {provider}")


def _build_corporate_actions_client(settings: Settings, provider: str):
    if provider == "alpha_vantage":
        return AlphaVantageCorporateActionsClient(api_key=settings.alpha_vantage_api_key)
    raise ProviderConfigError(f"Unsupported CORPORATE_ACTIONS_PROVIDER: {provider}")


def _build_peer_client(settings: Settings, provider: str):
    if provider == "finnhub":
        return FinnhubPeerUniverseClient(api_key=settings.finnhub_api_key)
    raise ProviderConfigError(f"Unsupported PEER_PROVIDER: {provider}")


def _build_contradiction_checker(provider: str):
    if provider == "rule_based":
        return RuleBasedContradictionChecker()
    raise ProviderConfigError(f"Unsupported CONTRADICTION_CHECKER_PROVIDER: {provider}")


def build_data_service(settings: Settings) -> DataService:
    """Build a data service with adapters chosen from runtime settings."""
    selection = resolve_provider_selection(settings)

    default_assumptions = {
        "inp_g1": settings.default_growth_year_1,
        "inp_g2": settings.default_growth_year_2,
        "inp_g3": settings.default_growth_year_3,
        "inp_g4": settings.default_growth_year_4,
        "inp_g5": settings.default_growth_year_5,
        "inp_m5": settings.default_margin_year_5,
        "inp_m10": settings.default_margin_year_10,
        "inp_tax_norm": settings.default_tax_norm,
        "inp_da_pct": settings.default_da_pct,
        "inp_capex_pct": settings.default_capex_pct,
        "inp_nwc_pct": settings.default_nwc_pct,
        "inp_rd_pct": settings.default_rd_pct,
        "inp_rent_pct": settings.default_rent_pct,
        "inp_gt": settings.default_terminal_growth,
        "inp_other_adj": settings.default_other_adjustment,
        "inp_cap_rd_toggle": settings.default_cap_rd_toggle,
        "inp_cap_lease_toggle": settings.default_cap_lease_toggle,
    }

    return DataService(
        fundamentals_client=_build_fundamentals_client(
            settings,
            selection.fundamentals_provider,
        ),
        market_client=_build_market_client(settings, selection.market_data_provider),
        rates_client=_build_rates_client(settings, selection.rates_provider),
        news_client=_build_news_client(settings, selection.news_provider),
        default_assumptions=default_assumptions,
    )


def build_research_service(settings: Settings) -> ResearchService:
    """Build the extended research service for phase-v1 mandatory tool set."""
    selection = resolve_research_provider_selection(settings)

    return ResearchService(
        news_client=_build_news_client(settings, selection.news_provider),
        transcript_client=_build_transcript_client(settings, selection.transcript_provider),
        corporate_actions_client=_build_corporate_actions_client(
            settings,
            selection.corporate_actions_provider
        ),
        peer_client=_build_peer_client(settings, selection.peer_provider),
        contradiction_checker=_build_contradiction_checker(
            selection.contradiction_checker_provider
        ),
    )
