"""Alpha Vantage corporate-actions adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from ..contracts import DataSourceCitation
from ..http_client import HttpJsonClient
from ..research_contracts import CorporateAction
from .client import CorporateActionsClient

ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"


def _parse_date(raw_value: Any) -> date | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_float(raw_value: Any) -> float | None:
    try:
        if raw_value in (None, ""):
            return None
        return float(raw_value)
    except (TypeError, ValueError):
        return None


@dataclass
class AlphaVantageCorporateActionsClient(CorporateActionsClient):
    """Fetches split/dividend events used in cap-table assumptions."""

    api_key: str
    http_client: HttpJsonClient = field(default_factory=HttpJsonClient)
    _citations: list[DataSourceCitation] = field(default_factory=list, init=False)

    def fetch_corporate_actions(self, ticker: str, limit: int = 50) -> list[CorporateAction]:
        if not self.api_key:
            raise RuntimeError(
                "ALPHA_VANTAGE_API_KEY is required for corporate-action fetches."
            )

        normalized_ticker = ticker.strip().upper()
        self._citations = []
        actions: list[CorporateAction] = []

        split_payload = self._request(function="SPLITS", symbol=normalized_ticker)
        self._record_citation(endpoint="SPLITS", note=f"symbol={normalized_ticker}")
        split_rows = split_payload.get("data")
        if isinstance(split_rows, list):
            for row in split_rows[: max(limit, 0)]:
                if not isinstance(row, dict):
                    continue
                factor = str(row.get("split_factor") or "")
                actions.append(
                    CorporateAction(
                        action_type="split",
                        announced_on=_parse_date(row.get("effective_date")),
                        effective_on=_parse_date(row.get("effective_date")),
                        description=f"Split factor {factor}".strip(),
                        magnitude=self._split_ratio_to_float(factor),
                        magnitude_unit="ratio",
                    )
                )

        dividend_payload = self._request(function="DIVIDENDS", symbol=normalized_ticker)
        self._record_citation(endpoint="DIVIDENDS", note=f"symbol={normalized_ticker}")
        dividend_rows = dividend_payload.get("data")
        if isinstance(dividend_rows, list):
            for row in dividend_rows[: max(limit, 0)]:
                if not isinstance(row, dict):
                    continue
                actions.append(
                    CorporateAction(
                        action_type="dividend",
                        announced_on=_parse_date(
                            row.get("declaration_date") or row.get("record_date")
                        ),
                        effective_on=_parse_date(
                            row.get("ex_dividend_date") or row.get("payment_date")
                        ),
                        description=str(row.get("dividend_type") or "Dividend"),
                        magnitude=_parse_float(row.get("amount")),
                        magnitude_unit="USD/share",
                    )
                )

        actions.sort(
            key=lambda item: (
                item.effective_on or date.min,
                item.announced_on or date.min,
            ),
            reverse=True,
        )
        return actions[: max(limit, 0)]

    def fetch_citations(self, ticker: str) -> list[DataSourceCitation]:
        if self._citations:
            return list(self._citations)
        return [
            DataSourceCitation(
                source="alpha_vantage",
                endpoint="SPLITS",
                url=ALPHA_VANTAGE_BASE_URL,
                accessed_at_utc=datetime.now(timezone.utc),
                note=f"Fallback corporate-actions citation for {ticker}.",
            )
        ]

    def _request(self, **params: Any) -> dict[str, Any]:
        query = dict(params)
        query["apikey"] = self.api_key
        payload = self.http_client.get_json(ALPHA_VANTAGE_BASE_URL, params=query)
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected Alpha Vantage corporate-actions response shape.")
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

    def _split_ratio_to_float(self, ratio: str) -> float | None:
        text = ratio.strip()
        if not text:
            return None
        if ":" not in text:
            return _parse_float(text)
        left, right = text.split(":", 1)
        lhs = _parse_float(left)
        rhs = _parse_float(right)
        if lhs is None or rhs in (None, 0):
            return None
        return lhs / rhs
