"""Execution API routes."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse, Response

from .artifact_store import MemoArtifactStore, is_gcs_reference, is_http_reference
from .models import ExecutionRecord
from .schemas import (
    DispatchExecutionResponse,
    ExecutionListResponse,
    ExecutionResponse,
    SubmitExecutionRequest,
)
from .service import ExecutionService

router = APIRouter(prefix="/api/v1", tags=["executions"])


@router.post(
    "/executions",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_execution(payload: SubmitExecutionRequest, request: Request) -> ExecutionResponse:
    service = _execution_service(request)
    try:
        execution = service.submit_execution(ticker=payload.ticker)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    _maybe_dispatch_after_submit(service)
    refreshed = service.get_execution(execution.id) or execution
    return _to_execution_response(refreshed, request)


@router.get("/executions", response_model=ExecutionListResponse)
def list_executions(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    ticker: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    from_utc: str | None = Query(default=None),
    to_utc: str | None = Query(default=None),
) -> ExecutionListResponse:
    service = _execution_service(request)
    try:
        rows, total = service.list_executions(
            page=page,
            page_size=page_size,
            ticker=ticker,
            status=status_filter,
            from_utc=from_utc,
            to_utc=to_utc,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return ExecutionListResponse(
        items=[_to_execution_response(row, request) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
def get_execution(execution_id: str, request: Request) -> ExecutionResponse:
    service = _execution_service(request)
    execution = service.get_execution(execution_id)
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found.",
        )
    return _to_execution_response(execution, request)


@router.get(
    "/executions/{execution_id}/memo.pdf",
    name="download_execution_memo",
    response_model=None,
)
def download_execution_memo(
    execution_id: str,
    request: Request,
) -> Response:
    service = _execution_service(request)
    execution = service.get_execution(execution_id)
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found.",
        )
    memo_path = str(execution.memo_pdf_path or "").strip()
    if not memo_path:
        reference = str(execution.memo_pdf_external_url or "").strip()
        if is_gcs_reference(reference):
            try:
                artifact = _memo_artifact_store(request).download(reference)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to fetch memo artifact for execution {execution_id}: {exc}",
                ) from exc
            filename = f"{execution.ticker}_{execution.run_id}_investment_memo.pdf"
            return Response(
                content=artifact.content,
                media_type=artifact.media_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )
        if is_http_reference(reference):
            return RedirectResponse(reference, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} does not have a memo PDF yet.",
        )

    resolved = Path(memo_path).resolve()
    allowed_root = (Path(request.app.state.repo_root) / "artifacts" / "memos").resolve()
    if not resolved.is_relative_to(allowed_root):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Memo artifact path is outside allowed directory.",
        )
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memo PDF file is missing for execution {execution_id}.",
        )

    filename = f"{execution.ticker}_{execution.run_id}_investment_memo.pdf"
    return FileResponse(
        resolved,
        media_type="application/pdf",
        filename=filename,
    )


@router.post(
    "/internal/dispatch-next",
    response_model=DispatchExecutionResponse,
)
def dispatch_next_execution(request: Request) -> DispatchExecutionResponse:
    _require_internal_dispatch_auth(request)
    service = _execution_service(request)
    try:
        execution = service.dispatch_next_queued_once()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Dispatch failed: {exc}",
        ) from exc

    if execution is None:
        return DispatchExecutionResponse(dispatched=False, execution=None)
    return DispatchExecutionResponse(
        dispatched=True,
        execution=_to_execution_response(execution, request),
    )


def _execution_service(request: Request) -> ExecutionService:
    service = getattr(request.app.state, "execution_service", None)
    if service is None:
        raise RuntimeError("Execution service not initialized.")
    return service


def _to_execution_response(
    execution: ExecutionRecord,
    request: Request,
) -> ExecutionResponse:
    memo_pdf_url = None
    if execution.memo_pdf_path or execution.memo_pdf_external_url:
        memo_pdf_url = _external_url_for(
            request,
            "download_execution_memo",
            execution_id=execution.id,
        )
    return ExecutionResponse(
        id=execution.id,
        run_id=execution.run_id,
        ticker=execution.ticker,
        company_name=execution.company_name,
        status=execution.status,
        submitted_at_utc=execution.submitted_at_utc,
        started_at_utc=execution.started_at_utc,
        finished_at_utc=execution.finished_at_utc,
        analyzed_at_utc=execution.analyzed_at_utc,
        google_sheets_url=execution.spreadsheet_url,
        memo_pdf_url=memo_pdf_url,
        error_message=execution.error_message,
    )


def _external_url_for(request: Request, route_name: str, **path_params: str) -> str:
    url = str(request.url_for(route_name, **path_params))
    forwarded_proto = _forwarded_proto(request)
    if not forwarded_proto:
        return url

    parts = urlsplit(url)
    if parts.scheme == forwarded_proto:
        return url
    return urlunsplit((forwarded_proto, parts.netloc, parts.path, parts.query, parts.fragment))


def _forwarded_proto(request: Request) -> str | None:
    raw = str(request.headers.get("x-forwarded-proto", "")).strip()
    if not raw:
        return None
    first = raw.split(",", 1)[0].strip().lower()
    if first in {"http", "https"}:
        return first
    return None


def _maybe_dispatch_after_submit(service: ExecutionService) -> None:
    if not service.uses_external_dispatch():
        return
    try:
        service.dispatch_next_queued_once()
    except Exception:
        # Submission should still succeed; the queued row will be retried by the dispatcher.
        return


def _require_internal_dispatch_auth(request: Request) -> None:
    token = str(getattr(request.app.state.settings, "execution_internal_auth_token", "") or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal dispatch token is not configured.",
        )

    header = str(request.headers.get("authorization", "")).strip()
    expected = f"Bearer {token}"
    if header != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized internal dispatch request.",
        )


def _memo_artifact_store(request: Request) -> MemoArtifactStore:
    store = getattr(request.app.state, "memo_artifact_store", None)
    if store is None:
        raise RuntimeError("Memo artifact store not initialized.")
    return store
