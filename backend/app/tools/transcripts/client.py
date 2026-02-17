"""Transcript tool interface for management-guidance analysis."""

from __future__ import annotations

from typing import Protocol

from ..contracts import DataSourceCitation
from ..research_contracts import TranscriptSignal


class TranscriptClient(Protocol):
    """Interface for transcript providers used by scenario reasoning."""

    def fetch_transcript_signals(self, ticker: str, limit: int = 20) -> list[TranscriptSignal]:
        """Fetch transcript-derived signals for assumptions/story linkage."""

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        """Return source citations for transcript retrieval."""
