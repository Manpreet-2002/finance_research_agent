"""SEC EDGAR client for filing-backed fundamentals and provenance."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from ..contracts import CompanyFundamentals, DataSourceCitation
from ..http_client import HttpJsonClient

SEC_BASE_URL = "https://data.sec.gov/api/xbrl/companyfacts"
SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

_FLOW_CONCEPTS_REVENUE: tuple[str, ...] = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "Revenue",
)
_FLOW_CONCEPTS_EBIT: tuple[str, ...] = (
    "OperatingIncomeLoss",
    "EarningsBeforeInterestAndTaxes",
)
_FLOW_CONCEPTS_TAX_EXPENSE: tuple[str, ...] = ("IncomeTaxExpenseBenefit",)
_FLOW_CONCEPTS_PRETAX_INCOME: tuple[str, ...] = ("IncomeBeforeTax",)
_FLOW_CONCEPTS_DA: tuple[str, ...] = (
    "DepreciationDepletionAndAmortization",
    "Depreciation",
)
_FLOW_CONCEPTS_CAPEX: tuple[str, ...] = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "CapitalExpendituresIncurredButNotYetPaid",
)
_FLOW_CONCEPTS_DNWC: tuple[str, ...] = (
    "IncreaseDecreaseInOperatingCapital",
    "IncreaseDecreaseInOperatingAssetsAndLiabilities",
    "IncreaseDecreaseInOperatingAssetsLiabilitiesNet",
)
_FLOW_CONCEPTS_RD: tuple[str, ...] = ("ResearchAndDevelopmentExpense",)
_FLOW_CONCEPTS_RENT: tuple[str, ...] = (
    "OperatingLeaseCost",
    "LeaseAndRentalExpense",
    "OperatingLeaseExpense",
)
_FLOW_CONCEPTS_DILUTED_SHARES: tuple[str, ...] = (
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingDiluted",
    "WeightedAverageNumberOfShareOutstandingDiluted",
)

_INSTANT_CONCEPTS_CASH: tuple[str, ...] = (
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsAndShortTermInvestments",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
)
_INSTANT_CONCEPTS_TOTAL_DEBT: tuple[str, ...] = (
    "DebtAndFinanceLeaseLiability",
    "DebtAndCapitalLeaseObligations",
    "LongTermDebtAndFinanceLeaseObligations",
    "LongTermDebtAndCapitalLeaseObligations",
    "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
)
_INSTANT_CONCEPTS_DEBT_COMPONENTS: tuple[str, ...] = (
    "LongTermDebtNoncurrent",
    "LongTermDebt",
    "DebtCurrent",
    "CurrentPortionOfLongTermDebt",
    "ShortTermBorrowings",
    "ShortTermDebt",
    "CommercialPaper",
)
_INSTANT_CONCEPTS_SHARES: tuple[str, ...] = (
    "EntityCommonStockSharesOutstanding",
    "CommonStockSharesOutstanding",
    "CommonStockSharesIssued",
)


class SecClient(Protocol):
    """Interface for SEC-backed company financial retrieval."""

    def fetch_company_fundamentals(self, ticker: str) -> CompanyFundamentals:
        """Fetch normalized TTM fundamentals from SEC-backed sources."""

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        """Return source citations for the latest fetch activity."""


@dataclass
class EdgarSecClient:
    """SEC EDGAR adapter using ticker map + companyfacts endpoints."""

    user_agent: str = "finance-research-agent/0.1"
    contact_email: str = ""
    http_client: HttpJsonClient = field(default_factory=HttpJsonClient)
    _citations: list[DataSourceCitation] = field(default_factory=list, init=False)

    def fetch_company_fundamentals(self, ticker: str) -> CompanyFundamentals:
        if not self.user_agent.strip():
            raise RuntimeError("SEC user agent is required for EDGAR requests.")

        self._citations = []
        normalized_ticker = ticker.strip().upper()
        company_meta = self._resolve_ticker_metadata(normalized_ticker)
        cik = int(company_meta["cik_str"])
        companyfacts = self._get_companyfacts(cik)

        revenue_ttm = self._latest_flow_ttm(companyfacts, _FLOW_CONCEPTS_REVENUE)
        ebit_ttm = self._latest_flow_ttm(companyfacts, _FLOW_CONCEPTS_EBIT)
        tax_expense_ttm = self._latest_flow_ttm(companyfacts, _FLOW_CONCEPTS_TAX_EXPENSE)
        pretax_income_ttm = self._latest_flow_ttm(
            companyfacts, _FLOW_CONCEPTS_PRETAX_INCOME
        )
        tax_rate_ttm = None
        if tax_expense_ttm is not None and pretax_income_ttm not in (None, 0):
            tax_rate_ttm = tax_expense_ttm / pretax_income_ttm
        if tax_rate_ttm is None:
            tax_rate_ttm = self._latest_instant_value(
                companyfacts,
                ("EffectiveIncomeTaxRateContinuingOperations",),
                unit="pure",
            )

        capex_ttm = self._latest_flow_ttm(companyfacts, _FLOW_CONCEPTS_CAPEX)
        if capex_ttm is not None:
            capex_ttm = abs(capex_ttm)

        debt_value = self._latest_instant_value(
            companyfacts,
            _INSTANT_CONCEPTS_TOTAL_DEBT,
            unit="USD",
        )
        if debt_value is None:
            debt_value = self._latest_instant_sum(
                companyfacts,
                _INSTANT_CONCEPTS_DEBT_COMPONENTS,
                unit="USD",
            )

        return CompanyFundamentals(
            ticker=normalized_ticker,
            company_name=str(company_meta.get("title") or normalized_ticker),
            currency="USD",
            revenue_ttm=revenue_ttm,
            ebit_ttm=ebit_ttm,
            tax_rate_ttm=tax_rate_ttm,
            da_ttm=self._latest_flow_ttm(companyfacts, _FLOW_CONCEPTS_DA),
            capex_ttm=capex_ttm,
            delta_nwc_ttm=self._latest_flow_ttm(companyfacts, _FLOW_CONCEPTS_DNWC),
            rd_ttm=self._latest_flow_ttm(companyfacts, _FLOW_CONCEPTS_RD),
            rent_ttm=self._latest_flow_ttm(companyfacts, _FLOW_CONCEPTS_RENT),
            cash=self._latest_instant_value(companyfacts, _INSTANT_CONCEPTS_CASH, unit="USD"),
            debt=debt_value,
            basic_shares=self._latest_instant_value(
                companyfacts,
                _INSTANT_CONCEPTS_SHARES,
                unit="shares",
            ),
            diluted_shares=self._latest_flow_value(
                companyfacts,
                _FLOW_CONCEPTS_DILUTED_SHARES,
                unit="shares",
            ),
        )

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        if self._citations:
            return list(self._citations)
        return [
            DataSourceCitation(
                source="sec_edgar",
                endpoint="companyfacts",
                url=SEC_BASE_URL,
                accessed_at_utc=datetime.now(timezone.utc),
                note=f"Fallback SEC citation for {ticker}.",
            )
        ]

    def _resolve_ticker_metadata(self, ticker: str) -> dict[str, Any]:
        payload = self.http_client.get_json(
            SEC_TICKER_MAP_URL,
            headers=self._sec_headers(),
        )
        self._record_citation(
            endpoint="company_tickers",
            url=SEC_TICKER_MAP_URL,
            note=f"ticker={ticker}",
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected SEC ticker map response shape.")

        for row in payload.values():
            if not isinstance(row, dict):
                continue
            if str(row.get("ticker", "")).strip().upper() == ticker:
                if row.get("cik_str") is None:
                    break
                return row
        raise RuntimeError(f"Ticker {ticker} not found in SEC ticker mapping.")

    def _get_companyfacts(self, cik: int) -> dict[str, Any]:
        cik_10 = str(cik).zfill(10)
        url = f"{SEC_BASE_URL}/CIK{cik_10}.json"
        payload = self.http_client.get_json(url, headers=self._sec_headers())
        self._record_citation(
            endpoint="companyfacts",
            url=url,
            note=f"cik={cik_10}",
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected SEC companyfacts response for CIK {cik_10}.")
        return payload

    def _latest_flow_ttm(
        self, payload: dict[str, Any], concept_names: tuple[str, ...]
    ) -> float | None:
        annual_values: list[dict[str, Any]] = []
        quarterly_values: list[dict[str, Any]] = []
        for concept in concept_names:
            for row in self._concept_rows(payload, concept, unit="USD"):
                if row.get("fp") == "FY":
                    annual_values.append(row)
                elif row.get("fp") in {"Q1", "Q2", "Q3", "Q4"}:
                    quarterly_values.append(row)

        annual_values = self._sorted_rows_desc(annual_values)
        if annual_values:
            return self._as_float(annual_values[0].get("val"))

        quarterly_values = self._sorted_rows_desc(quarterly_values)
        if not quarterly_values:
            return None

        ttm_rows = quarterly_values[:4]
        total = 0.0
        count = 0
        for row in ttm_rows:
            value = self._as_float(row.get("val"))
            if value is None:
                continue
            total += value
            count += 1
        if count == 0:
            return None
        return total

    def _latest_flow_value(
        self,
        payload: dict[str, Any],
        concept_names: tuple[str, ...],
        *,
        unit: str,
    ) -> float | None:
        rows: list[dict[str, Any]] = []
        for concept in concept_names:
            rows.extend(self._concept_rows(payload, concept, unit=unit))

        rows = self._sorted_rows_desc(rows)
        for row in rows:
            value = self._as_float(row.get("val"))
            if value is not None:
                return value
        return None

    def _latest_instant_value(
        self,
        payload: dict[str, Any],
        concept_names: tuple[str, ...],
        *,
        unit: str,
    ) -> float | None:
        rows: list[dict[str, Any]] = []
        for concept in concept_names:
            rows.extend(self._concept_rows(payload, concept, unit=unit))
        rows = self._sorted_rows_desc(rows)
        for row in rows:
            value = self._as_float(row.get("val"))
            if value is not None:
                return value
        return None

    def _latest_instant_sum(
        self,
        payload: dict[str, Any],
        concept_names: tuple[str, ...],
        *,
        unit: str,
    ) -> float | None:
        total = 0.0
        found = False
        for concept in concept_names:
            rows = self._sorted_rows_desc(self._concept_rows(payload, concept, unit=unit))
            for row in rows:
                value = self._as_float(row.get("val"))
                if value is None:
                    continue
                total += value
                found = True
                break
        if not found:
            return None
        return total

    def _concept_rows(
        self,
        payload: dict[str, Any],
        concept_name: str,
        *,
        unit: str,
    ) -> list[dict[str, Any]]:
        facts = payload.get("facts")
        if not isinstance(facts, dict):
            return []
        us_gaap = facts.get("us-gaap")
        if not isinstance(us_gaap, dict):
            return []
        concept = us_gaap.get(concept_name)
        if not isinstance(concept, dict):
            return []
        units = concept.get("units")
        if not isinstance(units, dict):
            return []
        rows = units.get(unit)
        if not isinstance(rows, list):
            return []
        clean_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            form = str(row.get("form", ""))
            if not form.startswith("10-K") and not form.startswith("10-Q"):
                continue
            clean_rows.append(row)
        return clean_rows

    def _sorted_rows_desc(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        def _key(row: dict[str, Any]) -> tuple[str, str]:
            end = str(row.get("end") or "")
            filed = str(row.get("filed") or "")
            return (end, filed)

        return sorted(rows, key=_key, reverse=True)

    def _sec_headers(self) -> dict[str, str]:
        contact = self.contact_email.strip()
        user_agent = self.user_agent.strip()
        if contact and contact not in user_agent:
            user_agent = f"{user_agent} ({contact})"
        return {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }

    def _record_citation(self, endpoint: str, url: str, note: str = "") -> None:
        self._citations.append(
            DataSourceCitation(
                source="sec_edgar",
                endpoint=endpoint,
                url=url,
                accessed_at_utc=datetime.now(timezone.utc),
                note=note,
            )
        )

    def _as_float(self, value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
