"""Unit tests for rule-based source contradiction checks."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.app.tools.contradiction_checker.client import RuleBasedContradictionChecker
from backend.app.tools.contracts import DataSourceCitation


def _citations() -> list[DataSourceCitation]:
    now = datetime.now(timezone.utc)
    return [
        DataSourceCitation(source="sec_edgar", endpoint="companyfacts", url="", accessed_at_utc=now),
        DataSourceCitation(source="finnhub", endpoint="stock/metric", url="", accessed_at_utc=now),
    ]


def test_checker_flags_material_numeric_mismatch() -> None:
    checker = RuleBasedContradictionChecker(numeric_relative_tolerance=0.10)
    facts = {
        "revenue_ttm": {
            "sec_edgar": 100.0,
            "finnhub": 140.0,
        }
    }

    flags = checker.check_contradictions("AAPL", facts=facts, citations=_citations())

    assert len(flags) == 1
    assert flags[0].metric_key == "revenue_ttm"
    assert flags[0].severity == "high"


def test_checker_ignores_small_numeric_difference() -> None:
    checker = RuleBasedContradictionChecker(numeric_relative_tolerance=0.10)
    facts = {
        "beta": {
            "finnhub": 1.1,
            "alpha_vantage": 1.15,
        }
    }

    flags = checker.check_contradictions("AAPL", facts=facts, citations=_citations())

    assert flags == []
