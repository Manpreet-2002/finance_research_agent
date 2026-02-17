"""Alpha Vantage transcript adapter for management-guidance signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..contracts import DataSourceCitation
from ..http_client import HttpJsonClient
from ..research_contracts import TranscriptSignal
from .client import TranscriptClient

ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"


@dataclass
class AlphaVantageTranscriptClient(TranscriptClient):
    """Fetches earnings-call transcript text and extracts directional signals."""

    api_key: str
    http_client: HttpJsonClient = field(default_factory=HttpJsonClient)
    _citations: list[DataSourceCitation] = field(default_factory=list, init=False)

    def fetch_transcript_signals(self, ticker: str, limit: int = 20) -> list[TranscriptSignal]:
        if not self.api_key:
            raise RuntimeError("ALPHA_VANTAGE_API_KEY is required for transcript fetches.")

        normalized_ticker = ticker.strip().upper()
        self._citations = []
        year, quarter = self._latest_fiscal_period(normalized_ticker)

        transcript_payload = self._request(
            function="EARNINGS_CALL_TRANSCRIPT",
            symbol=normalized_ticker,
            year=year,
            quarter=quarter,
        )
        self._record_citation(
            endpoint="EARNINGS_CALL_TRANSCRIPT",
            note=f"symbol={normalized_ticker} year={year} quarter={quarter}",
        )

        transcript_text = self._to_plain_text(transcript_payload.get("transcript"))
        if not transcript_text:
            return []
        return self._extract_signals(transcript_text, limit=max(1, limit))

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        if self._citations:
            return list(self._citations)
        return [
            DataSourceCitation(
                source="alpha_vantage",
                endpoint="EARNINGS_CALL_TRANSCRIPT",
                url=ALPHA_VANTAGE_BASE_URL,
                accessed_at_utc=datetime.now(timezone.utc),
                note=f"Fallback transcript citation for {ticker}.",
            )
        ]

    def _latest_fiscal_period(self, ticker: str) -> tuple[str, str]:
        payload = self._request(function="EARNINGS", symbol=ticker)
        self._record_citation(endpoint="EARNINGS", note=f"symbol={ticker}")

        quarter_rows = payload.get("quarterlyEarnings")
        if not isinstance(quarter_rows, list) or not quarter_rows:
            now = datetime.now(timezone.utc)
            return str(now.year), f"Q{((now.month - 1) // 3) + 1}"

        first = quarter_rows[0]
        if not isinstance(first, dict):
            now = datetime.now(timezone.utc)
            return str(now.year), f"Q{((now.month - 1) // 3) + 1}"

        fiscal_end = str(first.get("fiscalDateEnding") or "")
        try:
            fiscal_date = datetime.fromisoformat(fiscal_end)
        except ValueError:
            now = datetime.now(timezone.utc)
            return str(now.year), f"Q{((now.month - 1) // 3) + 1}"

        quarter_index = ((fiscal_date.month - 1) // 3) + 1
        return str(fiscal_date.year), f"Q{quarter_index}"

    def _request(self, **params: Any) -> dict[str, Any]:
        query = dict(params)
        query["apikey"] = self.api_key
        payload = self.http_client.get_json(ALPHA_VANTAGE_BASE_URL, params=query)
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected Alpha Vantage transcript response shape.")
        if payload.get("Error Message"):
            raise RuntimeError(str(payload["Error Message"]))
        return payload

    def _record_citation(self, endpoint: str, note: str = "") -> None:
        self._citations.append(
            DataSourceCitation(
                source="alpha_vantage",
                endpoint=endpoint,
                url=ALPHA_VANTAGE_BASE_URL,
                accessed_at_utc=datetime.now(timezone.utc),
                note=note,
            )
        )

    def _to_plain_text(self, transcript: Any) -> str:
        if transcript is None:
            return ""
        if isinstance(transcript, str):
            return transcript.strip()
        if isinstance(transcript, list):
            parts: list[str] = []
            for row in transcript:
                if isinstance(row, dict):
                    content = row.get("content")
                    if isinstance(content, str) and content.strip():
                        parts.append(content.strip())
                elif isinstance(row, str) and row.strip():
                    parts.append(row.strip())
            return " ".join(parts)
        return ""

    def _extract_signals(self, transcript_text: str, limit: int) -> list[TranscriptSignal]:
        lowered_sentences = self._split_sentences(transcript_text)
        if not lowered_sentences:
            return []

        topic_keywords: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("revenue_growth", ("revenue", "top line", "growth")),
            ("margin", ("margin", "profitability", "operating leverage")),
            ("demand", ("demand", "orders", "bookings", "pipeline")),
            ("guidance", ("guidance", "outlook", "expect", "forecast")),
            ("costs", ("cost", "expense", "inflation", "headcount")),
            ("capital_allocation", ("capex", "buyback", "dividend", "debt")),
        )
        positives = (
            "strong",
            "improve",
            "accelerat",
            "expand",
            "upside",
            "record",
            "robust",
        )
        negatives = (
            "pressure",
            "declin",
            "headwind",
            "soft",
            "uncertain",
            "weak",
            "challeng",
        )

        signals: list[TranscriptSignal] = []
        for topic, keywords in topic_keywords:
            matched_sentence = ""
            for sentence in lowered_sentences:
                if any(keyword in sentence for keyword in keywords):
                    matched_sentence = sentence
                    break
            if not matched_sentence:
                continue

            positive_hits = sum(token in matched_sentence for token in positives)
            negative_hits = sum(token in matched_sentence for token in negatives)
            if positive_hits > negative_hits:
                stance = "positive"
            elif negative_hits > positive_hits:
                stance = "negative"
            else:
                stance = "neutral"

            base_conf = 0.55
            if "guidance" in topic or "outlook" in matched_sentence:
                base_conf += 0.1
            if positive_hits or negative_hits:
                base_conf += 0.1
            confidence = min(base_conf, 0.85)

            signals.append(
                TranscriptSignal(
                    topic=topic,
                    stance=stance,
                    confidence=confidence,
                    evidence=matched_sentence[:360],
                )
            )
            if len(signals) >= limit:
                break
        return signals

    def _split_sentences(self, transcript_text: str) -> list[str]:
        normalized = " ".join(transcript_text.split())
        if not normalized:
            return []
        for delimiter in ("?", "!", ";"):
            normalized = normalized.replace(delimiter, ".")
        sentences = [part.strip().lower() for part in normalized.split(".")]
        return [sentence for sentence in sentences if len(sentence) >= 20]
