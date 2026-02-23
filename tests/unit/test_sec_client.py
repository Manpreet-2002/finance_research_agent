"""SEC EDGAR client regressions for share-count extraction."""

from __future__ import annotations

from backend.app.tools.sec.client import (
    EdgarSecClient,
    SEC_BASE_URL,
    SEC_TICKER_MAP_URL,
)


class _FakeHttpJsonClient:
    def __init__(self, *, ticker_map: dict, companyfacts: dict) -> None:
        self._ticker_map = ticker_map
        self._companyfacts = companyfacts
        self.calls: list[str] = []

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> dict:
        del headers
        self.calls.append(url)
        if url == SEC_TICKER_MAP_URL:
            return self._ticker_map
        if url.startswith(SEC_BASE_URL):
            return self._companyfacts
        raise AssertionError(f"Unexpected URL: {url}")


def _ticker_map_payload() -> dict:
    return {
        "0": {
            "ticker": "WMT",
            "cik_str": 104169,
            "title": "Walmart Inc.",
        }
    }


def test_sec_client_prefers_dei_entity_shares_over_stale_us_gaap() -> None:
    companyfacts = {
        "facts": {
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "val": 7_970_166_964,
                                "end": "2025-12-02",
                                "filed": "2025-12-03",
                                "form": "10-Q",
                                "fp": "Q3",
                                "fy": 2026,
                            }
                        ]
                    }
                }
            },
            "us-gaap": {
                "CommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "val": 3_418_000_000,
                                "end": "2012-01-31",
                                "filed": "2012-03-27",
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2011,
                            }
                        ]
                    }
                }
            },
        }
    }
    client = EdgarSecClient(
        user_agent="finance-research-agent-test/0.1",
        http_client=_FakeHttpJsonClient(
            ticker_map=_ticker_map_payload(),
            companyfacts=companyfacts,
        ),
    )

    fundamentals = client.fetch_company_fundamentals("WMT")

    assert fundamentals.basic_shares == 7_970_166_964


def test_sec_client_falls_back_to_us_gaap_when_dei_missing() -> None:
    companyfacts = {
        "facts": {
            "us-gaap": {
                "CommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "val": 4_250_000_000,
                                "end": "2025-12-31",
                                "filed": "2026-02-01",
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2025,
                            }
                        ]
                    }
                }
            },
        }
    }
    client = EdgarSecClient(
        user_agent="finance-research-agent-test/0.1",
        http_client=_FakeHttpJsonClient(
            ticker_map=_ticker_map_payload(),
            companyfacts=companyfacts,
        ),
    )

    fundamentals = client.fetch_company_fundamentals("WMT")

    assert fundamentals.basic_shares == 4_250_000_000


def test_sec_client_prefers_topline_revenue_concept_for_financial_filers() -> None:
    companyfacts = {
        "facts": {
            "us-gaap": {
                "RevenuesNetOfInterestExpense": {
                    "units": {
                        "USD": [
                            {
                                "val": 72_229_000_000,
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2025,
                            }
                        ]
                    }
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {
                                "val": 41_304_000_000,
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2025,
                            }
                        ]
                    }
                },
            }
        }
    }
    client = EdgarSecClient(
        user_agent="finance-research-agent-test/0.1",
        http_client=_FakeHttpJsonClient(
            ticker_map=_ticker_map_payload(),
            companyfacts=companyfacts,
        ),
    )

    fundamentals = client.fetch_company_fundamentals("WMT")

    assert fundamentals.revenue_ttm == 72_229_000_000


def test_sec_client_revenue_prefers_latest_period_then_priority_tiebreak() -> None:
    companyfacts = {
        "facts": {
            "us-gaap": {
                "RevenuesNetOfInterestExpense": {
                    "units": {
                        "USD": [
                            {
                                "val": 95_000_000_000,
                                "end": "2024-12-31",
                                "filed": "2025-02-15",
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2024,
                            }
                        ]
                    }
                },
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 120_000_000_000,
                                "end": "2025-12-31",
                                "filed": "2026-02-15",
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2025,
                            }
                        ]
                    }
                },
            }
        }
    }
    client = EdgarSecClient(
        user_agent="finance-research-agent-test/0.1",
        http_client=_FakeHttpJsonClient(
            ticker_map=_ticker_map_payload(),
            companyfacts=companyfacts,
        ),
    )

    fundamentals = client.fetch_company_fundamentals("WMT")

    assert fundamentals.revenue_ttm == 120_000_000_000
