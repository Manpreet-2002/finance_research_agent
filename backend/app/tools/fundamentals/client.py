"""Fundamentals provider interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..contracts import CompanyFundamentals, DataSourceCitation
from ..sec.client import EdgarSecClient


class FundamentalsClient(Protocol):
    """Interface for TTM fundamentals and capital-structure fields."""

    def fetch_company_fundamentals(self, ticker: str) -> CompanyFundamentals:
        """Fetch normalized company fundamentals for DCF inputs."""

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        """Return data-source citations for the last fundamentals fetch."""


@dataclass
class SecEdgarFundamentalsClient(EdgarSecClient):
    """SEC EDGAR-backed fundamentals adapter."""

    user_agent: str = "finance-research-agent/0.1"
    contact_email: str = ""
