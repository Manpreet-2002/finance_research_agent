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

    assert fundamentals.revenue_ttm == 1_000.0
    assert fundamentals.ebit_ttm == 150.0
