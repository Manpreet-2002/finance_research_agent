"""Shared tool-layer contracts for data collection and canonicalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

DEFAULT_DCF_INPUT_ASSUMPTIONS: dict[str, Any] = {
    "inp_g1": 0.05,
    "inp_g2": 0.04,
    "inp_g3": 0.03,
    "inp_g4": 0.03,
    "inp_g5": 0.03,
    "inp_m5": 0.30,
    "inp_m10": 0.30,
    "inp_tax_norm": 0.18,
    "inp_da_pct": 0.03,
    "inp_capex_pct": 0.02,
    "inp_nwc_pct": 0.00,
    "inp_rd_pct": 0.07,
    "inp_rent_pct": 0.01,
    "inp_gt": 0.025,
    "inp_cap_rd_toggle": "YES",
    "inp_cap_lease_toggle": "YES",
    "inp_other_adj": 0.0,
}

REQUIRED_DCF_INPUT_RANGES: tuple[str, ...] = (
    "inp_ticker",
    "inp_name",
    "inp_rev_ttm",
    "inp_ebit_ttm",
    "inp_tax_ttm",
    "inp_da_ttm",
    "inp_capex_ttm",
    "inp_dNWC_ttm",
    "inp_rd_ttm",
    "inp_rent_ttm",
    "inp_g1",
    "inp_g2",
    "inp_g3",
    "inp_g4",
    "inp_g5",
    "inp_m5",
    "inp_m10",
    "inp_tax_norm",
    "inp_da_pct",
    "inp_capex_pct",
    "inp_nwc_pct",
    "inp_rd_pct",
    "inp_rent_pct",
    "inp_rf",
    "inp_erp",
    "inp_beta",
    "inp_kd",
    "inp_dw",
    "inp_gt",
    "inp_cash",
    "inp_debt",
    "inp_other_adj",
    "inp_basic_shares",
    "inp_px",
    "inp_cap_rd_toggle",
    "inp_cap_lease_toggle",
    "inp_tsm_tranche1_count_mm",
    "inp_tsm_tranche1_strike",
    "inp_tsm_tranche1_type",
    "inp_tsm_tranche1_note",
)


@dataclass(frozen=True)
class DataSourceCitation:
    """Source metadata attached to fetched values and assumptions."""

    source: str
    endpoint: str
    url: str
    accessed_at_utc: datetime
    note: str = ""


@dataclass(frozen=True)
class CompanyFundamentals:
    """Core financial and capital structure fields used by DCF inputs."""

    ticker: str
    company_name: str
    currency: str
    revenue_ttm: float | None
    ebit_ttm: float | None
    tax_rate_ttm: float | None
    da_ttm: float | None
    capex_ttm: float | None
    delta_nwc_ttm: float | None
    rd_ttm: float | None
    rent_ttm: float | None
    cash: float | None
    debt: float | None
    basic_shares: float | None
    diluted_shares: float | None = None


@dataclass(frozen=True)
class MarketSnapshot:
    """Market-derived fields used in valuation assumptions."""

    ticker: str
    price: float | None
    beta: float | None
    market_cap: float | None
    shares_outstanding: float | None
    captured_at_utc: datetime


@dataclass(frozen=True)
class RatesSnapshot:
    """Risk and discount-rate inputs for cost of capital."""

    risk_free_rate: float | None
    equity_risk_premium: float | None
    cost_of_debt: float | None
    debt_weight: float | None
    captured_at_utc: datetime


@dataclass(frozen=True)
class NewsItem:
    """Top-level catalyst/risk context for memo generation."""

    headline: str
    publisher: str
    published_at_utc: datetime | None
    url: str
    summary: str = ""


@dataclass(frozen=True)
class TsmSnapshot:
    """Canonical TSM prefill signals derived from company share data."""

    average_share_price: float | None
    basic_shares_mm: float
    diluted_shares_mm: float | None
    incremental_shares_mm: float
    diluted_source: str
    tranche1_count_mm: float
    tranche1_type: str = "RSU"
    tranche1_strike: float | None = None
    tranche1_note: str = ""


@dataclass(frozen=True)
class CanonicalValuationDataset:
    """Normalized, source-traceable payload for sheets + memo flows."""

    ticker: str
    fundamentals: CompanyFundamentals
    market: MarketSnapshot
    rates: RatesSnapshot
    news: list[NewsItem] = field(default_factory=list)
    citations: list[DataSourceCitation] = field(default_factory=list)
    assumptions: dict[str, Any] = field(default_factory=dict)
    tsm: TsmSnapshot | None = None

    @staticmethod
    def _to_sheet_money_mm(value: float | None) -> float | None:
        """Normalize monetary values to USD millions for the template contract."""
        if value is None:
            return None
        numeric = float(value)
        if abs(numeric) >= 1_000_000:
            return numeric / 1_000_000
        return numeric

    @classmethod
    def _normalize_shares_mm(
        cls,
        raw_shares: float | None,
        market_cap: float | None,
        price: float | None,
    ) -> float:
        """Normalize share count to millions using market-consistency when possible."""
        implied_candidates = cls._implied_shares_mm_candidates(
            market_cap=market_cap, price=price
        )
        if raw_shares is None:
            if implied_candidates:
                # Market providers used in V1 expose market cap in USD mm.
                return implied_candidates[0]
            return 0.0

        raw = float(raw_shares)
        if 1 <= abs(raw) < 1_000_000:
            return raw

        if implied_candidates:
            raw_candidates = [raw, raw / 1_000_000]
            best_error = float("inf")
            best_shares = raw
            for share_candidate in raw_candidates:
                for implied in implied_candidates:
                    if implied <= 0:
                        continue
                    error = abs(share_candidate - implied) / implied
                    if error < best_error:
                        best_error = error
                        best_shares = share_candidate
            if best_error <= 0.5:
                return best_shares

        # Fallback heuristic for sources that provide absolute share count.
        if abs(raw) >= 1_000_000:
            return raw / 1_000_000
        return raw

    @classmethod
    def _implied_shares_mm_candidates(
        cls, market_cap: float | None, price: float | None
    ) -> list[float]:
        if market_cap in (None, 0) or price in (None, 0):
            return []
        market_cap_value = float(market_cap)
        price_value = float(price)
        # Candidate 1: market cap already in USD mm (Finnhub profile2 convention).
        implied_mm = market_cap_value / price_value
        # Candidate 2: market cap in USD absolute.
        implied_from_absolute = (market_cap_value / 1_000_000) / price_value
        return [implied_mm, implied_from_absolute]

    @classmethod
    def derive_tsm_snapshot(
        cls,
        *,
        fundamentals: CompanyFundamentals,
        market: MarketSnapshot,
    ) -> TsmSnapshot:
        """Derive TSM prefill values from basic/diluted share signals."""
        basic_raw = fundamentals.basic_shares or market.shares_outstanding
        basic_mm = cls._normalize_shares_mm(
            raw_shares=basic_raw,
            market_cap=market.market_cap,
            price=market.price,
        )

        diluted_raw = fundamentals.diluted_shares
        diluted_source = "fundamentals.diluted_shares"
        if diluted_raw is None:
            diluted_raw = market.shares_outstanding
            diluted_source = "market.shares_outstanding"

        diluted_mm: float | None = None
        if diluted_raw is not None:
            diluted_mm = cls._normalize_shares_mm(
                raw_shares=diluted_raw,
                market_cap=market.market_cap,
                price=market.price,
            )

        incremental_mm = 0.0
        note = "No diluted-share source; prefilled zero incremental shares."
        if diluted_mm is not None:
            incremental_mm = max(0.0, float(diluted_mm) - float(basic_mm))
            note = (
                "Prefill from diluted-basic share gap "
                f"({diluted_source}); tranche type=RSU."
            )

        return TsmSnapshot(
            average_share_price=market.price,
            basic_shares_mm=basic_mm,
            diluted_shares_mm=diluted_mm,
            incremental_shares_mm=incremental_mm,
            diluted_source=diluted_source,
            tranche1_count_mm=incremental_mm,
            tranche1_type="RSU",
            tranche1_strike=None,
            tranche1_note=note,
        )

    def to_sheets_named_ranges(self) -> dict[str, Any]:
        """Map canonical fields to the current DCF template named ranges."""
        assumptions = {**DEFAULT_DCF_INPUT_ASSUMPTIONS, **(self.assumptions or {})}
        tax_ttm = self.fundamentals.tax_rate_ttm
        if tax_ttm is None:
            tax_ttm = assumptions["inp_tax_norm"]

        cash_value = (
            self._to_sheet_money_mm(self.fundamentals.cash)
            if self.fundamentals.cash is not None
            else 0.0
        )
        debt_value = (
            self._to_sheet_money_mm(self.fundamentals.debt)
            if self.fundamentals.debt is not None
            else 0.0
        )
        shares_value = self._normalize_shares_mm(
            raw_shares=self.fundamentals.basic_shares or self.market.shares_outstanding,
            market_cap=self.market.market_cap,
            price=self.market.price,
        )

        rd_ttm = self.fundamentals.rd_ttm
        if rd_ttm is None and self.fundamentals.revenue_ttm is not None:
            rd_ttm = self.fundamentals.revenue_ttm * assumptions["inp_rd_pct"]

        rent_ttm = self.fundamentals.rent_ttm
        if rent_ttm is None and self.fundamentals.revenue_ttm is not None:
            rent_ttm = self.fundamentals.revenue_ttm * assumptions["inp_rent_pct"]

        da_ttm = self.fundamentals.da_ttm
        if da_ttm is None and self.fundamentals.revenue_ttm is not None:
            da_ttm = self.fundamentals.revenue_ttm * assumptions["inp_da_pct"]

        capex_ttm = self.fundamentals.capex_ttm
        if capex_ttm is None and self.fundamentals.revenue_ttm is not None:
            capex_ttm = self.fundamentals.revenue_ttm * assumptions["inp_capex_pct"]

        delta_nwc_ttm = self.fundamentals.delta_nwc_ttm
        if delta_nwc_ttm is None and self.fundamentals.revenue_ttm is not None:
            delta_nwc_ttm = self.fundamentals.revenue_ttm * assumptions["inp_nwc_pct"]
        if delta_nwc_ttm is None:
            delta_nwc_ttm = 0.0

        named_ranges = {
            "inp_ticker": self.ticker,
            "inp_name": self.fundamentals.company_name,
            "inp_rev_ttm": self._to_sheet_money_mm(self.fundamentals.revenue_ttm),
            "inp_ebit_ttm": self._to_sheet_money_mm(self.fundamentals.ebit_ttm),
            "inp_tax_ttm": tax_ttm,
            "inp_da_ttm": self._to_sheet_money_mm(da_ttm),
            "inp_capex_ttm": self._to_sheet_money_mm(capex_ttm),
            "inp_dNWC_ttm": self._to_sheet_money_mm(delta_nwc_ttm),
            "inp_rd_ttm": self._to_sheet_money_mm(rd_ttm),
            "inp_rent_ttm": self._to_sheet_money_mm(rent_ttm),
            "inp_cash": cash_value,
            "inp_debt": debt_value,
            "inp_basic_shares": shares_value,
            "inp_px": self.market.price,
            "inp_rf": self.rates.risk_free_rate,
            "inp_erp": self.rates.equity_risk_premium,
            "inp_beta": self.market.beta,
            "inp_kd": self.rates.cost_of_debt,
            "inp_dw": self.rates.debt_weight,
            "inp_gt": assumptions["inp_gt"],
            "inp_g1": assumptions["inp_g1"],
            "inp_g2": assumptions["inp_g2"],
            "inp_g3": assumptions["inp_g3"],
            "inp_g4": assumptions["inp_g4"],
            "inp_g5": assumptions["inp_g5"],
            "inp_m5": assumptions["inp_m5"],
            "inp_m10": assumptions["inp_m10"],
            "inp_tax_norm": assumptions["inp_tax_norm"],
            "inp_da_pct": assumptions["inp_da_pct"],
            "inp_capex_pct": assumptions["inp_capex_pct"],
            "inp_nwc_pct": assumptions["inp_nwc_pct"],
            "inp_rd_pct": assumptions["inp_rd_pct"],
            "inp_rent_pct": assumptions["inp_rent_pct"],
            "inp_other_adj": assumptions["inp_other_adj"],
            "inp_cap_rd_toggle": assumptions["inp_cap_rd_toggle"],
            "inp_cap_lease_toggle": assumptions["inp_cap_lease_toggle"],
        }

        tsm_snapshot = self.tsm or self.derive_tsm_snapshot(
            fundamentals=self.fundamentals,
            market=self.market,
        )
        named_ranges.update(
            {
                "inp_tsm_tranche1_count_mm": tsm_snapshot.tranche1_count_mm,
                "inp_tsm_tranche1_strike": (
                    ""
                    if tsm_snapshot.tranche1_strike is None
                    else tsm_snapshot.tranche1_strike
                ),
                "inp_tsm_tranche1_type": tsm_snapshot.tranche1_type,
                "inp_tsm_tranche1_note": tsm_snapshot.tranche1_note,
            }
        )

        return named_ranges
