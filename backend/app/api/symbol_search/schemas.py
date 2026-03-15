"""Pydantic schemas for symbol lookup responses."""

from __future__ import annotations

from pydantic import BaseModel


class SymbolSearchResultResponse(BaseModel):
    ticker: str
    company_name: str
    label: str


class SymbolSearchResponse(BaseModel):
    query: str
    total: int
    items: list[SymbolSearchResultResponse]
