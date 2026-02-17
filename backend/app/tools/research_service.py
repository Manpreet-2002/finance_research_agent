"""Unified research-service facade for phase-v1 mandatory tools."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from time import perf_counter
from typing import Any, Callable, TypeVar

from .contracts import DataSourceCitation, NewsItem
from .contradiction_checker.client import ContradictionChecker
from .corporate_actions.client import CorporateActionsClient
from .news.client import NewsClient
from .peer.client import PeerUniverseClient
from .research_contracts import ResearchPacket
from .transcripts.client import TranscriptClient

_T = TypeVar("_T")


@dataclass
class ResearchService:
    """Collects non-core research streams for story/comps/consistency work."""

    news_client: NewsClient
    transcript_client: TranscriptClient
    corporate_actions_client: CorporateActionsClient
    peer_client: PeerUniverseClient
    contradiction_checker: ContradictionChecker
    _logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("finance_research_agent.tools.research_service"),
        init=False,
        repr=False,
    )

    def build_research_packet(
        self,
        ticker: str,
        facts: dict[str, Any] | None = None,
        news_limit: int = 12,
    ) -> ResearchPacket:
        """Gather extended research context for phase-v1 memo and checks."""
        started = perf_counter()
        self._logger.info(
            "research_packet_start ticker=%s news_limit=%s facts_keys=%s",
            ticker,
            news_limit,
            ",".join(sorted((facts or {}).keys())[:20]),
        )
        safe_facts = dict(facts or {})

        news = self._safe_call(lambda: self.news_client.fetch_company_news(ticker, limit=news_limit), [])
        transcript_signals = self._safe_call(
            lambda: self.transcript_client.fetch_transcript_signals(ticker), []
        )
        corporate_actions = self._safe_call(
            lambda: self.corporate_actions_client.fetch_corporate_actions(ticker), []
        )
        peers = self._safe_call(lambda: self.peer_client.discover_peers(ticker), [])

        citations: list[DataSourceCitation] = []
        citations.extend(self._safe_call(lambda: self.news_client.fetch_citations(ticker), []))
        citations.extend(
            self._safe_call(lambda: self.transcript_client.fetch_citations(ticker), [])
        )
        citations.extend(
            self._safe_call(lambda: self.corporate_actions_client.fetch_citations(ticker), [])
        )
        citations.extend(self._safe_call(lambda: self.peer_client.fetch_citations(ticker), []))

        contradictions = self._safe_call(
            lambda: self.contradiction_checker.check_contradictions(
                ticker=ticker,
                facts=safe_facts,
                citations=citations,
            ),
            [],
        )

        packet = ResearchPacket(
            ticker=ticker,
            news=list(news) if isinstance(news, list) else [],
            transcript_signals=list(transcript_signals)
            if isinstance(transcript_signals, list)
            else [],
            corporate_actions=list(corporate_actions)
            if isinstance(corporate_actions, list)
            else [],
            peers=list(peers) if isinstance(peers, list) else [],
            contradictions=list(contradictions) if isinstance(contradictions, list) else [],
            citations=list(citations),
        )
        elapsed_ms = (perf_counter() - started) * 1000.0
        self._logger.info(
            "research_packet_end ticker=%s news=%s transcripts=%s corp_actions=%s peers=%s contradictions=%s citations=%s elapsed_ms=%.2f",
            ticker,
            len(packet.news),
            len(packet.transcript_signals),
            len(packet.corporate_actions),
            len(packet.peers),
            len(packet.contradictions),
            len(packet.citations),
            elapsed_ms,
        )
        return packet

    def _safe_call(self, fn: Callable[[], _T], default: _T) -> _T:
        try:
            return fn()
        except Exception as exc:
            self._logger.warning(
                "research_provider_degraded error=%s default_type=%s",
                exc,
                type(default).__name__,
            )
            return default
