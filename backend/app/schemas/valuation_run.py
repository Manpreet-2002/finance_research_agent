"""Core run schemas used by orchestration and tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValuationRunRequest:
    ticker: str
    run_id: str
    overrides: dict[str, Any]
    template_filename: str = (
        "Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx"
    )


@dataclass(frozen=True)
class ValuationRunResult:
    run_id: str
    status: str
    value_per_share: float | None
    equity_value: float | None
    enterprise_value: float | None
    notes: str = ""
    spreadsheet_id: str | None = None
    memo_markdown: str = ""
    citations_summary: dict[str, int] | None = None
    pending_questions: tuple[str, ...] = ()
    phases_executed: tuple[str, ...] = ()
    skills_planned: dict[str, tuple[str, ...]] | None = None
