"""Unit tests for Finnhub fundamentals normalization behavior."""

from __future__ import annotations

from backend.app.tools.fundamentals.finnhub import FinnhubFundamentalsClient


def _quarter(
    *,
    revenue: float,
    ebit: float,
    tax_expense: float,
    pretax: float,
    da: float,
    capex: float,
    d_nwc: float,
    rd: float,
    cash: float,
    debt: float,
) -> dict[str, object]:
    return {
        "report": {
            "ic": [
                {
                    "concept": "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
                    "value": revenue,
                },
                {"concept": "us-gaap_OperatingIncomeLoss", "value": ebit},
                {"concept": "us-gaap_IncomeTaxExpenseBenefit", "value": tax_expense},
                {"concept": "us-gaap_IncomeBeforeTax", "value": pretax},
                {"concept": "us-gaap_ResearchAndDevelopmentExpense", "value": rd},
            ],
            "cf": [
                {
                    "concept": "us-gaap_DepreciationDepletionAndAmortization",
                    "value": da,
                },
                {
                    "concept": "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment",
                    "value": capex,
                },
                {
                    "concept": "us-gaap_IncreaseDecreaseInOperatingCapital",
                    "value": d_nwc,
                },
            ],
            "bs": [
                {
                    "concept": "us-gaap_CashAndCashEquivalentsAtCarryingValue",
                    "value": cash,
                },
                {"concept": "us-gaap_LongTermDebtNoncurrent", "value": debt},
            ],
        }
    }


def test_build_fundamentals_parses_taxonomy_prefixed_concepts() -> None:
    client = FinnhubFundamentalsClient(api_key="test-key")
    profile = {"name": "Example Corp", "currency": "USD", "shareOutstanding": 100.0}
    metrics = {"metric": {"shareOutstanding": 100.0}}
    reported = {
        "data": [
            _quarter(
                revenue=100.0,
                ebit=10.0,
                tax_expense=2.0,
                pretax=12.0,
                da=3.0,
                capex=-4.0,
                d_nwc=1.0,
                rd=5.0,
                cash=50.0,
                debt=20.0,
            )
            for _ in range(4)
        ]
    }

    fundamentals = client._build_fundamentals(
        ticker="TEST",
        profile=profile,
        metrics=metrics,
        reported=reported,
    )

    assert fundamentals.revenue_ttm == 400.0
    assert fundamentals.ebit_ttm == 40.0
    assert fundamentals.tax_rate_ttm == 2.0 / 12.0
    assert fundamentals.da_ttm == 12.0
    assert fundamentals.capex_ttm == 16.0
    assert fundamentals.delta_nwc_ttm == 4.0
    assert fundamentals.rd_ttm == 20.0
    assert fundamentals.cash == 50.0
    assert fundamentals.debt == 20.0


def test_build_fundamentals_falls_back_to_metric_revenue_and_margin() -> None:
    client = FinnhubFundamentalsClient(api_key="test-key")
    profile = {"name": "Example Corp", "currency": "USD", "shareOutstanding": 100.0}
    metrics = {
        "metric": {
            "shareOutstanding": 100.0,
            "revenuePerShareTTM": 10.0,
            "operatingMarginTTM": 15.0,
        }
    }
    reported = {"data": []}

    fundamentals = client._build_fundamentals(
        ticker="TEST",
        profile=profile,
        metrics=metrics,
        reported=reported,
    )

    assert fundamentals.revenue_ttm == 1_000_000_000.0
    assert fundamentals.ebit_ttm == 150_000_000.0


def test_build_fundamentals_uses_metric_fallback_when_quarters_insufficient() -> None:
    client = FinnhubFundamentalsClient(api_key="test-key")
    profile = {"name": "Example Corp", "currency": "USD", "shareOutstanding": 100.0}
    metrics = {
        "metric": {
            "shareOutstanding": 100.0,
            "revenuePerShareTTM": 10.0,
            "operatingMarginTTM": 20.0,
        }
    }
    reported = {
        "data": [
            {
                **_quarter(
                    revenue=40.0,
                    ebit=6.0,
                    tax_expense=1.0,
                    pretax=7.0,
                    da=2.0,
                    capex=-3.0,
                    d_nwc=0.5,
                    rd=1.0,
                    cash=10.0,
                    debt=5.0,
                ),
                "startDate": "2025-07-01",
                "endDate": "2025-09-30",
                "fiscalPeriod": "Q3",
            },
            {
                **_quarter(
                    revenue=40.0,
                    ebit=6.0,
                    tax_expense=1.0,
                    pretax=7.0,
                    da=2.0,
                    capex=-3.0,
                    d_nwc=0.5,
                    rd=1.0,
                    cash=10.0,
                    debt=5.0,
                ),
                "startDate": "2025-10-01",
                "endDate": "2025-12-31",
                "fiscalPeriod": "Q4",
            },
        ]
    }

    fundamentals = client._build_fundamentals(
        ticker="TEST",
        profile=profile,
        metrics=metrics,
        reported=reported,
    )

    assert fundamentals.revenue_ttm == 1_000_000_000.0
    assert fundamentals.ebit_ttm == 200_000_000.0


def test_build_fundamentals_ignores_annual_row_when_quarter_rows_present() -> None:
    client = FinnhubFundamentalsClient(api_key="test-key")
    profile = {"name": "Example Corp", "currency": "USD", "shareOutstanding": 100.0}
    metrics = {"metric": {"shareOutstanding": 100.0}}
    reported = {
        "data": [
            {
                **_quarter(
                    revenue=9999.0,
                    ebit=999.0,
                    tax_expense=99.0,
                    pretax=1098.0,
                    da=0.0,
                    capex=0.0,
                    d_nwc=0.0,
                    rd=0.0,
                    cash=1.0,
                    debt=1.0,
                ),
                "startDate": "2024-01-01",
                "endDate": "2024-12-31",
                "fiscalPeriod": "FY",
            },
            {
                **_quarter(
                    revenue=100.0,
                    ebit=10.0,
                    tax_expense=2.0,
                    pretax=12.0,
                    da=1.0,
                    capex=-1.0,
                    d_nwc=0.0,
                    rd=1.0,
                    cash=5.0,
                    debt=2.0,
                ),
                "startDate": "2025-01-01",
                "endDate": "2025-03-31",
                "fiscalPeriod": "Q1",
            },
            {
                **_quarter(
                    revenue=100.0,
                    ebit=10.0,
                    tax_expense=2.0,
                    pretax=12.0,
                    da=1.0,
                    capex=-1.0,
                    d_nwc=0.0,
                    rd=1.0,
                    cash=5.0,
                    debt=2.0,
                ),
                "startDate": "2025-04-01",
                "endDate": "2025-06-30",
                "fiscalPeriod": "Q2",
            },
            {
                **_quarter(
                    revenue=100.0,
                    ebit=10.0,
                    tax_expense=2.0,
                    pretax=12.0,
                    da=1.0,
                    capex=-1.0,
                    d_nwc=0.0,
                    rd=1.0,
                    cash=5.0,
                    debt=2.0,
                ),
                "startDate": "2025-07-01",
                "endDate": "2025-09-30",
                "fiscalPeriod": "Q3",
            },
            {
                **_quarter(
                    revenue=100.0,
                    ebit=10.0,
                    tax_expense=2.0,
                    pretax=12.0,
                    da=1.0,
                    capex=-1.0,
                    d_nwc=0.0,
                    rd=1.0,
                    cash=5.0,
                    debt=2.0,
                ),
                "startDate": "2025-10-01",
                "endDate": "2025-12-31",
                "fiscalPeriod": "Q4",
            },
        ]
    }

    fundamentals = client._build_fundamentals(
        ticker="TEST",
        profile=profile,
        metrics=metrics,
        reported=reported,
    )

    assert fundamentals.revenue_ttm == 400.0
    assert fundamentals.ebit_ttm == 40.0
