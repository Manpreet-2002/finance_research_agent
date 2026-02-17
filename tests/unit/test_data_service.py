"""Unit scaffolding for data-service aggregation behavior."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.app.tools.contracts import (
    CanonicalValuationDataset,
    CompanyFundamentals,
    DataSourceCitation,
    MarketSnapshot,
    NewsItem,
    RatesSnapshot,
)
from backend.app.tools.data_service import DataService


class _FakeFundamentalsClient:
    def fetch_company_fundamentals(self, ticker: str) -> CompanyFundamentals:
        return CompanyFundamentals(
            ticker=ticker,
            company_name="Example Corp",
            currency="USD",
            revenue_ttm=100.0,
            ebit_ttm=20.0,
            tax_rate_ttm=0.21,
            da_ttm=3.0,
            capex_ttm=5.0,
            delta_nwc_ttm=1.0,
            rd_ttm=2.0,
            rent_ttm=1.0,
            cash=10.0,
            debt=30.0,
            basic_shares=50.0,
            diluted_shares=52.0,
        )

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        now = datetime.now(timezone.utc)
        return [DataSourceCitation("sec", "facts", "", now)]


class _FakeMarketClient:
    def fetch_market_snapshot(self, ticker: str) -> MarketSnapshot:
        now = datetime.now(timezone.utc)
        return MarketSnapshot(
            ticker=ticker,
            price=42.0,
            beta=1.1,
            market_cap=2_100.0,
            shares_outstanding=50.0,
            captured_at_utc=now,
        )

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        now = datetime.now(timezone.utc)
        return [DataSourceCitation("market", "quote", "", now)]


class _FakeRatesClient:
    def fetch_rates_snapshot(self) -> RatesSnapshot:
        now = datetime.now(timezone.utc)
        return RatesSnapshot(
            risk_free_rate=0.0425,
            equity_risk_premium=0.05,
            cost_of_debt=0.055,
            debt_weight=0.1,
            captured_at_utc=now,
        )

    def fetch_citations(self) -> list[DataSourceCitation]:
        now = datetime.now(timezone.utc)
        return [DataSourceCitation("rates", "fred", "", now)]


class _FakeNewsClient:
    def fetch_company_news(self, ticker: str, limit: int = 10) -> list[NewsItem]:
        return [
            NewsItem(
                headline=f"{ticker} headline",
                publisher="TestWire",
                published_at_utc=datetime.now(timezone.utc),
                url="https://example.com",
            )
        ]

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        now = datetime.now(timezone.utc)
        return [DataSourceCitation("news", "headlines", "", now)]


def test_data_service_builds_canonical_dataset() -> None:
    service = DataService(
        fundamentals_client=_FakeFundamentalsClient(),
        market_client=_FakeMarketClient(),
        rates_client=_FakeRatesClient(),
        news_client=_FakeNewsClient(),
    )

    dataset = service.build_canonical_dataset("AAPL")

    assert dataset.ticker == "AAPL"
    assert dataset.fundamentals.company_name == "Example Corp"
    assert dataset.market.price == 42.0
    assert dataset.rates.risk_free_rate == 0.0425
    assert len(dataset.news) == 1
    assert len(dataset.citations) == 4
    assert dataset.to_sheets_named_ranges()["inp_ticker"] == "AAPL"
    assert dataset.to_sheets_named_ranges()["inp_rd_ttm"] == 2.0
    assert dataset.tsm is not None
    assert dataset.to_sheets_named_ranges()["inp_tsm_tranche1_type"] == "RSU"


def test_to_sheets_named_ranges_normalizes_money_and_shares_units() -> None:
    now = datetime.now(timezone.utc)
    dataset = CanonicalValuationDataset(
        ticker="GOOG",
        fundamentals=CompanyFundamentals(
            ticker="GOOG",
            company_name="Alphabet Inc",
            currency="USD",
            revenue_ttm=97_786_000_000.0,
            ebit_ttm=27_544_000_000.0,
            tax_rate_ttm=0.18,
            da_ttm=3_598_000_000.0,
            capex_ttm=6_728_000_000.0,
            delta_nwc_ttm=0.0,
            rd_ttm=13_363_000_000.0,
            rent_ttm=977_860_000.0,
            cash=16_260_000_000.0,
            debt=6_206_000_000.0,
            basic_shares=12_097_000_000.0,
            diluted_shares=12_350_000_000.0,
        ),
        market=MarketSnapshot(
            ticker="GOOG",
            price=306.02,
            beta=1.12,
            market_cap=3_700_285.5,
            shares_outstanding=12_097.0,
            captured_at_utc=now,
        ),
        rates=RatesSnapshot(
            risk_free_rate=0.0409,
            equity_risk_premium=0.05,
            cost_of_debt=0.055,
            debt_weight=0.10,
            captured_at_utc=now,
        ),
    )

    named = dataset.to_sheets_named_ranges()
    assert named["inp_rev_ttm"] == 97_786.0
    assert named["inp_ebit_ttm"] == 27_544.0
    assert named["inp_cash"] == 16_260.0
    assert named["inp_debt"] == 6_206.0
    assert named["inp_basic_shares"] == 12_097.0
    assert named["inp_tsm_tranche1_count_mm"] == 253.0
    assert named["inp_tsm_tranche1_type"] == "RSU"


def test_to_sheets_named_ranges_falls_back_da_and_capex_from_assumptions() -> None:
    now = datetime.now(timezone.utc)
    dataset = CanonicalValuationDataset(
        ticker="AMZN",
        fundamentals=CompanyFundamentals(
            ticker="AMZN",
            company_name="Amazon.com Inc",
            currency="USD",
            revenue_ttm=1_000_000_000.0,
            ebit_ttm=100_000_000.0,
            tax_rate_ttm=0.20,
            da_ttm=None,
            capex_ttm=None,
            delta_nwc_ttm=None,
            rd_ttm=None,
            rent_ttm=None,
            cash=50_000_000.0,
            debt=10_000_000.0,
            basic_shares=10_000_000.0,
            diluted_shares=10_500_000.0,
        ),
        market=MarketSnapshot(
            ticker="AMZN",
            price=100.0,
            beta=1.1,
            market_cap=1_000_000.0,
            shares_outstanding=10_000.0,
            captured_at_utc=now,
        ),
        rates=RatesSnapshot(
            risk_free_rate=0.04,
            equity_risk_premium=0.05,
            cost_of_debt=0.055,
            debt_weight=0.1,
            captured_at_utc=now,
        ),
    )

    named = dataset.to_sheets_named_ranges()
    assert named["inp_da_ttm"] == 30.0
    assert named["inp_capex_ttm"] == 20.0
