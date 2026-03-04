"""Domain models for valuation execution API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

ExecutionStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
VALID_EXECUTION_STATUSES: tuple[ExecutionStatus, ...] = (
    "QUEUED",
    "RUNNING",
    "COMPLETED",
    "FAILED",
)


@dataclass(frozen=True)
class ExecutionRecord:
    """Persistent execution record used by API and worker."""

    id: str
    run_id: str
    ticker: str
    company_name: str | None
    status: ExecutionStatus
    submitted_at_utc: str
    started_at_utc: str | None
    finished_at_utc: str | None
    spreadsheet_id: str | None
    spreadsheet_url: str | None
    memo_pdf_path: str | None
    memo_pdf_external_url: str | None
    job_execution_name: str | None
    error_message: str | None
    created_at_utc: str
    updated_at_utc: str

    @property
    def analyzed_at_utc(self) -> str:
        return (
            self.finished_at_utc
            or self.started_at_utc
            or self.submitted_at_utc
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
