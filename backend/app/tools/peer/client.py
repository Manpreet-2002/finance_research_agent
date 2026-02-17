"""Peer discovery tool interface for comps and competitive analysis."""

from __future__ import annotations

from typing import Protocol

from ..contracts import DataSourceCitation
from ..research_contracts import PeerCompany


class PeerUniverseClient(Protocol):
    """Interface for sector/industry mapping and peer-set generation."""

    def discover_peers(self, ticker: str, limit: int = 12) -> list[PeerCompany]:
        """Return a relevance-ranked peer list for the target ticker."""

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        """Return source citations for peer discovery."""
