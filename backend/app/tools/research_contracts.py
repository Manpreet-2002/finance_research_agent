"""Contracts for mandatory phase-v1 research tools beyond base market/rates data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .contracts import DataSourceCitation, NewsItem


@dataclass(frozen=True)
class TranscriptSignal:
    """Extracted guidance signal from earnings transcripts."""

    topic: str
    stance: str
    confidence: float
    evidence: str


@dataclass(frozen=True)
class CorporateAction:
    """Corporate action impacting valuation assumptions or share count."""

    action_type: str
    announced_on: date | None
    effective_on: date | None
    description: str
    magnitude: float | None = None
    magnitude_unit: str = ""


@dataclass(frozen=True)
class PeerCompany:
    """Peer company selected for competitive and relative valuation context."""

    ticker: str
    company_name: str
    industry: str
    rationale: str


@dataclass(frozen=True)
class ContradictionFlag:
    """Potential conflict identified across sources for the same fact."""

    metric_key: str
    source_a: str
    source_b: str
    message: str
    severity: str = "medium"


@dataclass(frozen=True)
class ResearchPacket:
    """Unified packet for story/comps/sensitivity reasoning workflows."""

    ticker: str
    news: list[NewsItem] = field(default_factory=list)
    transcript_signals: list[TranscriptSignal] = field(default_factory=list)
    corporate_actions: list[CorporateAction] = field(default_factory=list)
    peers: list[PeerCompany] = field(default_factory=list)
    contradictions: list[ContradictionFlag] = field(default_factory=list)
    citations: list[DataSourceCitation] = field(default_factory=list)
