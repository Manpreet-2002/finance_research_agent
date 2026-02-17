"""FRED rates adapter for risk-free input."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..contracts import DataSourceCitation, RatesSnapshot
from ..http_client import HttpJsonClient
from .client import RatesClient

FRED_BASE_URL = "https://api.stlouisfed.org/fred"


def _as_float(value: Any) -> float | None:
    try:
        if value in (None, "", "."):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class FredRatesClient(RatesClient):
    """Fetches risk-free rate from FRED and applies configured defaults."""

    api_key: str
    rf_series_id: str = "DGS10"
    default_equity_risk_premium: float = 0.05
    default_cost_of_debt: float = 0.055
    default_debt_weight: float = 0.10
    http_client: HttpJsonClient = field(default_factory=HttpJsonClient)
    _citations: list[DataSourceCitation] = field(default_factory=list, init=False)

    def fetch_rates_snapshot(self) -> RatesSnapshot:
        if not self.api_key:
            raise RuntimeError("FRED_API_KEY is required for rates fetches.")

        risk_free_rate = self._fetch_latest_series_value(self.rf_series_id)
        return RatesSnapshot(
            risk_free_rate=risk_free_rate,
            equity_risk_premium=self.default_equity_risk_premium,
            cost_of_debt=self.default_cost_of_debt,
            debt_weight=self.default_debt_weight,
            captured_at_utc=datetime.now(timezone.utc),
        )

    def fetch_citations(self) -> list[DataSourceCitation]:
        if self._citations:
            return list(self._citations)
        return [
            DataSourceCitation(
                source="fred",
                endpoint="series/observations",
                url=f"{FRED_BASE_URL}/series/observations",
                accessed_at_utc=datetime.now(timezone.utc),
                note=f"Fallback citation for series_id={self.rf_series_id}; unit=decimal.",
            )
        ]

    def _fetch_latest_series_value(self, series_id: str) -> float | None:
        endpoint = "series/observations"
        payload = self.http_client.get_json(
            f"{FRED_BASE_URL}/{endpoint}",
            params={
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 10,
            },
        )
        self._citations = [
            DataSourceCitation(
                source="fred",
                endpoint=endpoint,
                url=f"{FRED_BASE_URL}/{endpoint}",
                accessed_at_utc=datetime.now(timezone.utc),
                note=f"series_id={series_id}; source_unit=percent; normalized=decimal",
            )
        ]

        if not isinstance(payload, dict):
            return None

        observations = payload.get("observations")
        if not isinstance(observations, list):
            return None

        for row in observations:
            if not isinstance(row, dict):
                continue
            raw_value = _as_float(row.get("value"))
            if raw_value is None:
                continue
            # FRED Treasury series are percent values; convert to decimal.
            return raw_value / 100.0
        return None
