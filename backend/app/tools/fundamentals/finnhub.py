"""Finnhub fundamentals adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..contracts import CompanyFundamentals, DataSourceCitation
from ..http_client import HttpJsonClient
from .client import FundamentalsClient

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def _as_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_number(mapping: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        result = _as_float(mapping.get(key))
        if result is not None:
            return result
    return None


def _concept_matches(concept: str, concept_names: set[str]) -> bool:
    """Match taxonomy-prefixed concept IDs against bare concept names."""
    normalized_names = {str(name).strip().casefold() for name in concept_names if name}
    raw = str(concept or "").strip()
    if not raw:
        return False
    candidates = {raw.casefold()}
    if "_" in raw:
        candidates.add(raw.split("_", 1)[1].casefold())
    if ":" in raw:
        candidates.add(raw.split(":", 1)[1].casefold())
    return any(candidate in normalized_names for candidate in candidates)


def _extract_concept_total(
    entries: list[dict[str, Any]], concept_names: set[str]
) -> float | None:
    values: list[float] = []
    for entry in entries:
        concept = str(entry.get("concept", "")).strip()
        if not _concept_matches(concept, concept_names):
            continue
        numeric = _as_float(entry.get("value"))
        if numeric is not None:
            values.append(numeric)
    if not values:
        return None
    return float(sum(values))


def _extract_first_concept_value(
    entries: list[dict[str, Any]], concept_names: set[str]
) -> float | None:
    for entry in entries:
        concept = str(entry.get("concept", "")).strip()
        if not _concept_matches(concept, concept_names):
            continue
        numeric = _as_float(entry.get("value"))
        if numeric is not None:
            return numeric
    return None


@dataclass
class FinnhubFundamentalsClient(FundamentalsClient):
    """Fetches company fundamentals from Finnhub endpoints."""

    api_key: str
    http_client: HttpJsonClient = field(default_factory=HttpJsonClient)
    _citations: list[DataSourceCitation] = field(default_factory=list, init=False)

    def fetch_company_fundamentals(self, ticker: str) -> CompanyFundamentals:
        if not self.api_key:
            raise RuntimeError(
                "FINNHUB_API_KEY is required for Finnhub fundamentals client."
            )

        self._citations = []
        profile = self._get_profile(ticker)
        metrics = self._get_metrics(ticker)
        reported = self._get_financials_reported(ticker)

        fundamentals = self._build_fundamentals(
            ticker=ticker, profile=profile, metrics=metrics, reported=reported
        )
        return fundamentals

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        if self._citations:
            return list(self._citations)
        now = datetime.now(timezone.utc)
        return [
            DataSourceCitation(
                source="finnhub",
                endpoint="stock/profile2",
                url=f"{FINNHUB_BASE_URL}/stock/profile2",
                accessed_at_utc=now,
                note=f"Fallback citation for {ticker}; units=USD and shares.",
            )
        ]

    def _build_fundamentals(
        self,
        ticker: str,
        profile: dict[str, Any],
        metrics: dict[str, Any],
        reported: dict[str, Any],
    ) -> CompanyFundamentals:
        metric_values = metrics.get("metric") or {}
        reported_rows = reported.get("data") or []
        latest_quarters = reported_rows[:4]

        revenue_ttm = self._sum_quarterly_ic(
            latest_quarters,
            {
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "Revenues",
                "SalesRevenueNet",
                "Revenue",
            },
        )
        ebit_ttm = self._sum_quarterly_ic(
            latest_quarters,
            {"OperatingIncomeLoss", "EarningsBeforeInterestAndTaxes"},
        )
        if revenue_ttm is None:
            revenue_ttm = self._metric_revenue_ttm(metric_values, profile)
        if ebit_ttm is None:
            ebit_ttm = self._metric_ebit_ttm(metric_values, revenue_ttm)

        tax_expense_ttm = self._sum_quarterly_ic(
            latest_quarters,
            {"IncomeTaxExpenseBenefit", "IncomeTaxesPaidNet"},
        )
        pretax_income_ttm = self._sum_quarterly_ic(
            latest_quarters,
            {"IncomeBeforeTax", "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"},
        )
        tax_rate_ttm = None
        if tax_expense_ttm is not None and pretax_income_ttm not in (None, 0):
            tax_rate_ttm = tax_expense_ttm / pretax_income_ttm

        da_ttm = self._sum_quarterly_cf(
            latest_quarters,
            {"DepreciationDepletionAndAmortization", "Depreciation"},
        )
        rd_ttm = self._sum_quarterly_ic(
            latest_quarters,
            {
                "ResearchAndDevelopmentExpense",
                "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
            },
        )
        rent_ttm = self._sum_quarterly_ic(
            latest_quarters,
            {
                "OperatingLeaseExpense",
                "LeaseAndRentalExpense",
                "OperatingLeaseCost",
            },
        )

        capex_raw = self._sum_quarterly_cf(
            latest_quarters,
            {
                "PaymentsToAcquirePropertyPlantAndEquipment",
                "CapitalExpenditure",
                "PurchaseOfPropertyPlantAndEquipment",
            },
        )
        capex_ttm = abs(capex_raw) if capex_raw is not None else None

        delta_nwc_ttm = self._sum_quarterly_cf(
            latest_quarters,
            {
                "IncreaseDecreaseInOperatingCapital",
                "IncreaseDecreaseInOperatingAssetsLiabilitiesNet",
                "IncreaseDecreaseInOperatingAssetsAndLiabilities",
            },
        )

        cash_latest = self._latest_quarter_bs_value(
            reported_rows,
            {
                "CashAndCashEquivalentsAtCarryingValue",
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                "Cash",
                "CashCashEquivalentsAndShortTermInvestments",
            },
        )
        debt_latest = (
            self._latest_quarter_bs_value(
                reported_rows,
                {
                    "DebtAndCapitalLeaseObligations",
                    "LongTermDebtAndCapitalLeaseObligations",
                    "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
                },
            )
            or self._latest_quarter_bs_sum(
                reported_rows,
                {
                    "LongTermDebtNoncurrent",
                    "LongTermDebt",
                    "DebtCurrent",
                    "CurrentPortionOfLongTermDebt",
                    "ShortTermBorrowings",
                    "ShortTermDebt",
                    "CommercialPaper",
                },
            )
        )
        diluted_shares = _first_number(
            metric_values,
            [
                "dilutedSharesOutstanding",
                "sharesOutstandingDiluted",
                "weightedAverageShsOutDil",
            ],
        ) or self._latest_quarter_ic_value(
            reported_rows,
            {
                "WeightedAverageNumberOfDilutedSharesOutstanding",
                "WeightedAverageNumberOfSharesOutstandingDiluted",
                "WeightedAverageNumberOfShareOutstandingDiluted",
            },
        )

        if tax_rate_ttm is None:
            tax_rate_ttm = _first_number(
                metric_values,
                [
                    "effectiveTaxRateTTM",
                    "taxRateAnnual",
                ],
            )

        return CompanyFundamentals(
            ticker=ticker,
            company_name=str(profile.get("name") or ticker),
            currency=str(profile.get("currency") or "USD"),
            revenue_ttm=revenue_ttm,
            ebit_ttm=ebit_ttm,
            tax_rate_ttm=tax_rate_ttm,
            da_ttm=da_ttm,
            capex_ttm=capex_ttm,
            delta_nwc_ttm=delta_nwc_ttm,
            rd_ttm=rd_ttm,
            rent_ttm=rent_ttm,
            cash=cash_latest
            or _first_number(metric_values, ["totalCash"])
            or self._cash_from_cash_per_share(metric_values, profile),
            debt=debt_latest
            or _first_number(metric_values, ["totalDebt", "longTermDebtTotal"]),
            basic_shares=_first_number(
                metric_values,
                ["shareOutstanding", "sharesOutstanding"],
            )
            or _as_float(profile.get("shareOutstanding")),
            diluted_shares=diluted_shares,
        )

    def _sum_quarterly_ic(
        self, quarters: list[dict[str, Any]], concept_names: set[str]
    ) -> float | None:
        return self._sum_quarterly_section(quarters, "ic", concept_names)

    def _sum_quarterly_cf(
        self, quarters: list[dict[str, Any]], concept_names: set[str]
    ) -> float | None:
        return self._sum_quarterly_section(quarters, "cf", concept_names)

    def _sum_quarterly_section(
        self, quarters: list[dict[str, Any]], section: str, concept_names: set[str]
    ) -> float | None:
        values: list[float] = []
        for item in quarters:
            report = item.get("report") or {}
            entries = report.get(section) or []
            concept_total = _extract_concept_total(entries, concept_names)
            if concept_total is not None:
                values.append(concept_total)
        if not values:
            return None
        return float(sum(values))

    def _latest_quarter_bs_value(
        self, quarters: list[dict[str, Any]], concept_names: set[str]
    ) -> float | None:
        for item in quarters:
            report = item.get("report") or {}
            entries = report.get("bs") or []
            result = _extract_first_concept_value(entries, concept_names)
            if result is not None:
                return result
        return None

    def _latest_quarter_bs_sum(
        self, quarters: list[dict[str, Any]], concept_names: set[str]
    ) -> float | None:
        for item in quarters:
            report = item.get("report") or {}
            entries = report.get("bs") or []
            total = _extract_concept_total(entries, concept_names)
            if total is not None:
                return total
        return None

    def _latest_quarter_ic_value(
        self, quarters: list[dict[str, Any]], concept_names: set[str]
    ) -> float | None:
        for item in quarters:
            report = item.get("report") or {}
            entries = report.get("ic") or []
            value = _extract_first_concept_value(entries, concept_names)
            if value is not None:
                return value
        return None

    def _cash_from_cash_per_share(
        self, metric_values: dict[str, Any], profile: dict[str, Any]
    ) -> float | None:
        cash_per_share = _first_number(metric_values, ["cashPerShare"])
        shares = self._shares_for_metric_fallback(metric_values, profile)
        if cash_per_share is None or shares is None:
            return None
        return cash_per_share * shares

    def _shares_for_metric_fallback(
        self, metric_values: dict[str, Any], profile: dict[str, Any]
    ) -> float | None:
        return _first_number(metric_values, ["shareOutstanding", "sharesOutstanding"]) or _as_float(
            profile.get("shareOutstanding")
        )

    def _metric_revenue_ttm(
        self, metric_values: dict[str, Any], profile: dict[str, Any]
    ) -> float | None:
        revenue_per_share = _first_number(
            metric_values,
            ["revenuePerShareTTM", "revenuePerShareAnnual"],
        )
        shares = self._shares_for_metric_fallback(metric_values, profile)
        if revenue_per_share is None or shares is None:
            return None
        return revenue_per_share * shares

    def _metric_ebit_ttm(
        self, metric_values: dict[str, Any], revenue_ttm: float | None
    ) -> float | None:
        if revenue_ttm is None:
            return None
        operating_margin = _first_number(
            metric_values,
            ["operatingMarginTTM", "operatingMarginAnnual"],
        )
        if operating_margin is None:
            return None
        margin = operating_margin / 100.0 if abs(operating_margin) > 1 else operating_margin
        return revenue_ttm * margin

    def _get_profile(self, ticker: str) -> dict[str, Any]:
        endpoint = "stock/profile2"
        data = self._request(endpoint, {"symbol": ticker})
        self._record_citation(endpoint)
        return data if isinstance(data, dict) else {}

    def _get_metrics(self, ticker: str) -> dict[str, Any]:
        endpoint = "stock/metric"
        data = self._request(endpoint, {"symbol": ticker, "metric": "all"})
        self._record_citation(endpoint)
        return data if isinstance(data, dict) else {}

    def _get_financials_reported(self, ticker: str) -> dict[str, Any]:
        endpoint = "stock/financials-reported"
        data = self._request(endpoint, {"symbol": ticker, "freq": "quarterly"})
        self._record_citation(endpoint)
        return data if isinstance(data, dict) else {}

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any] | list[Any]:
        query = dict(params)
        query["token"] = self.api_key
        return self.http_client.get_json(f"{FINNHUB_BASE_URL}/{endpoint}", params=query)

    def _record_citation(self, endpoint: str) -> None:
        self._citations.append(
            DataSourceCitation(
                source="finnhub",
                endpoint=endpoint,
                url=f"{FINNHUB_BASE_URL}/{endpoint}",
                accessed_at_utc=datetime.now(timezone.utc),
                note="unit=provider_native",
            )
        )
