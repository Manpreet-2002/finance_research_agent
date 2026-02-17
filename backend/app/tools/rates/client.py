"""Rates interfaces for risk-free rate, ERP, and debt assumptions."""

from __future__ import annotations

from typing import Protocol

from ..contracts import DataSourceCitation, RatesSnapshot


class RatesClient(Protocol):
    """Interface for macro/rate data providers."""

    def fetch_rates_snapshot(self) -> RatesSnapshot:
        """Fetch rate assumptions used in cost of capital."""

    def fetch_citations(self) -> list[DataSourceCitation]:
        """Return source citations for rates endpoints used."""
