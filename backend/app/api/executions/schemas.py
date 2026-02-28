"""Pydantic schemas for execution API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SubmitExecutionRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10, description="US equity ticker symbol.")


class ExecutionResponse(BaseModel):
    id: str
    run_id: str
    ticker: str
    company_name: str | None
    status: str
    submitted_at_utc: str
    started_at_utc: str | None
    finished_at_utc: str | None
    analyzed_at_utc: str
    google_sheets_url: str | None
    memo_pdf_url: str | None
    error_message: str | None


class ExecutionListResponse(BaseModel):
    items: list[ExecutionResponse]
    total: int
    page: int
    page_size: int
