"""Corporate actions tool interface for cap-table and dilution support."""

from __future__ import annotations

from typing import Protocol

from ..contracts import DataSourceCitation
from ..research_contracts import CorporateAction


class CorporateActionsClient(Protocol):
    """Interface for splits, buybacks, issuance, and dividend history."""

    def fetch_corporate_actions(self, ticker: str, limit: int = 50) -> list[CorporateAction]:
        """Fetch actions relevant to valuation and share-count assumptions."""

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        """Return source citations for corporate-action retrieval."""
