"""Finnhub peer-universe adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..contracts import DataSourceCitation
from ..http_client import HttpJsonClient
from ..research_contracts import PeerCompany
from .client import PeerUniverseClient

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


@dataclass
class FinnhubPeerUniverseClient(PeerUniverseClient):
    """Discovers peer tickers and enriches with company profile metadata."""

    api_key: str
    http_client: HttpJsonClient = field(default_factory=HttpJsonClient)
    _citations: list[DataSourceCitation] = field(default_factory=list, init=False)

    def discover_peers(self, ticker: str, limit: int = 12) -> list[PeerCompany]:
        if not self.api_key:
            raise RuntimeError("FINNHUB_API_KEY is required for peer discovery.")

        normalized_ticker = ticker.strip().upper()
        self._citations = []
        target_profile = self._request("stock/profile2", {"symbol": normalized_ticker})
        target_industry = str(target_profile.get("finnhubIndustry") or "").strip()

        peer_payload = self._request("stock/peers", {"symbol": normalized_ticker})
        peers_raw: list[str] = []
        if isinstance(peer_payload, list):
            peers_raw = [str(item).strip().upper() for item in peer_payload]

        peers: list[PeerCompany] = []
        for peer_ticker in peers_raw:
            if not peer_ticker or peer_ticker == normalized_ticker:
                continue
            profile = self._request("stock/profile2", {"symbol": peer_ticker})
            peer_industry = str(profile.get("finnhubIndustry") or "").strip()
            rationale = "Peer from Finnhub peer-universe set."
            if target_industry and peer_industry:
                if target_industry == peer_industry:
                    rationale = (
                        f"Peer from Finnhub set with matching industry: {peer_industry}."
                    )
                else:
                    rationale = (
                        "Peer from Finnhub set with adjacent industry mapping "
                        f"({peer_industry} vs {target_industry})."
                    )
            peers.append(
                PeerCompany(
                    ticker=peer_ticker,
                    company_name=str(profile.get("name") or peer_ticker),
                    industry=peer_industry or target_industry,
                    rationale=rationale,
                )
            )
            if len(peers) >= max(limit, 0):
                break
        return peers

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        if self._citations:
            return list(self._citations)
        return [
            DataSourceCitation(
                source="finnhub",
                endpoint="stock/peers",
                url=f"{FINNHUB_BASE_URL}/stock/peers",
                accessed_at_utc=datetime.now(timezone.utc),
                note=f"Fallback peer citation for {ticker}.",
            )
        ]

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any] | list[Any]:
        query = dict(params)
        query["token"] = self.api_key
        response = self.http_client.get_json(f"{FINNHUB_BASE_URL}/{endpoint}", params=query)
        self._citations.append(
            DataSourceCitation(
                source="finnhub",
                endpoint=endpoint,
                url=f"{FINNHUB_BASE_URL}/{endpoint}",
                accessed_at_utc=datetime.now(timezone.utc),
                note=f"unit=provider_native ticker={params.get('symbol', '')}",
            )
        )
        if isinstance(response, (dict, list)):
            return response
        return {}
