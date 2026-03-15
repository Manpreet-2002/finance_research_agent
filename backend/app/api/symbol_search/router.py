"""Symbol search API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status

from ...tools.symbol_search.client import SymbolSearchServiceProtocol
from .schemas import SymbolSearchResponse, SymbolSearchResultResponse

router = APIRouter(prefix="/api/v1", tags=["symbol-search"])


@router.get("/symbol-search", response_model=SymbolSearchResponse)
def search_symbols(
    request: Request,
    q: str = Query(min_length=1, description="Partial ticker or company name."),
    limit: int = Query(default=10, ge=1, le=10),
) -> SymbolSearchResponse:
    service = _symbol_search_service(request)
    try:
        matches = service.search(q, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return SymbolSearchResponse(
        query=q,
        total=len(matches),
        items=[
            SymbolSearchResultResponse(
                ticker=row.ticker,
                company_name=row.company_name,
                label=row.label,
            )
            for row in matches
        ],
    )


def _symbol_search_service(request: Request) -> SymbolSearchServiceProtocol:
    service = getattr(request.app.state, "symbol_search_service", None)
    if service is None:
        raise RuntimeError("Symbol search service not initialized.")
    return service
