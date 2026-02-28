"""Execution service that runs valuation jobs from queue."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import logging
from pathlib import Path
import re
from threading import Event, Thread
from typing import Any

from ...core.settings import Settings
from ...memo.post_run_memo import MemoWrapperResult, PostRunMemoService
from ...orchestrator.valuation_runner import ValuationRunner
from ...schemas.valuation_run import ValuationRunRequest, ValuationRunResult
from .models import ExecutionRecord
from .store import ExecutionStore

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


@dataclass(frozen=True)
class ExecutionServiceConfig:
    poll_seconds: float = 1.0
    worker_enabled: bool = True
    max_workers: int = 1


class ExecutionService:
    """Submission and background execution runner for valuation requests."""

    def __init__(
        self,
        *,
        settings: Settings,
        store: ExecutionStore,
        config: ExecutionServiceConfig,
        repo_root: Path | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.config = config
        self.repo_root = repo_root or Path(__file__).resolve().parents[4]
        self._logger = logging.getLogger("finance_research_agent.api.execution_service")
        self._stop_event = Event()
        self._worker_thread: Thread | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._inflight_futures: set[Future[None]] = set()

    def start(self) -> None:
        if not self.config.worker_enabled:
            self._logger.info("execution_worker_disabled")
            return
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._inflight_futures.clear()
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, self.config.max_workers),
            thread_name_prefix="execution-runner",
        )
        self._worker_thread = Thread(
            target=self._worker_loop,
            name="execution-worker",
            daemon=True,
        )
        self._worker_thread.start()
        self._logger.info(
            "execution_worker_started poll_seconds=%s max_workers=%s",
            self.config.poll_seconds,
            max(1, self.config.max_workers),
        )

    def shutdown(self) -> None:
        self._stop_event.set()
        worker = self._worker_thread
        if worker and worker.is_alive():
            worker.join(timeout=5)
        self._drain_completed_futures()
        executor = self._executor
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
        self._executor = None
        self._inflight_futures.clear()
        self._worker_thread = None
        self._logger.info("execution_worker_stopped")

    def submit_execution(self, *, ticker: str) -> ExecutionRecord:
        normalized = self._normalize_ticker(ticker)
        return self.store.create_execution(ticker=normalized)

    def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        return self.store.get_execution(execution_id)

    def list_executions(
        self,
        *,
        page: int,
        page_size: int,
        ticker: str | None,
        status: str | None,
        from_utc: str | None,
        to_utc: str | None,
    ) -> tuple[list[ExecutionRecord], int]:
        normalized_ticker = self._normalize_ticker(ticker) if ticker else None
        normalized_status = self._normalize_status(status) if status else None
        return self.store.list_executions(
            page=page,
            page_size=page_size,
            ticker=normalized_ticker,
            status=normalized_status,
            from_utc=from_utc,
            to_utc=to_utc,
        )

    def run_next_queued_once(self) -> ExecutionRecord | None:
        claimed = self.store.claim_next_queued()
        if claimed is None:
            return None
        self._process_claimed_execution(claimed)
        return self.store.get_execution(claimed.id)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            self._drain_completed_futures()

            available_slots = max(1, self.config.max_workers) - len(self._inflight_futures)
            if available_slots <= 0:
                self._stop_event.wait(max(0.1, self.config.poll_seconds))
                continue

            dispatched = 0
            for _ in range(available_slots):
                claimed = self.store.claim_next_queued()
                if claimed is None:
                    break
                self._submit_claimed_execution(claimed)
                dispatched += 1

            if dispatched == 0:
                self._stop_event.wait(max(0.1, self.config.poll_seconds))

    def _submit_claimed_execution(self, execution: ExecutionRecord) -> None:
        executor = self._executor
        if executor is None:
            raise RuntimeError("Execution worker pool is not initialized.")
        future = executor.submit(self._process_claimed_execution, execution)
        self._inflight_futures.add(future)
        self._logger.info(
            "execution_dispatched execution_id=%s run_id=%s ticker=%s inflight=%s",
            execution.id,
            execution.run_id,
            execution.ticker,
            len(self._inflight_futures),
        )

    def _drain_completed_futures(self) -> None:
        if not self._inflight_futures:
            return
        completed = [future for future in self._inflight_futures if future.done()]
        for future in completed:
            self._inflight_futures.discard(future)
            try:
                future.result()
            except Exception:  # noqa: BLE001
                self._logger.exception("execution_worker_future_failed")

    def _process_claimed_execution(self, execution: ExecutionRecord) -> None:
        self._logger.info(
            "execution_start execution_id=%s run_id=%s ticker=%s",
            execution.id,
            execution.run_id,
            execution.ticker,
        )
        runner: ValuationRunner | None = None
        result: ValuationRunResult | None = None
        memo_result: MemoWrapperResult | None = None
        try:
            request = ValuationRunRequest(
                ticker=execution.ticker,
                run_id=execution.run_id,
                overrides={"log_status": "RUNNING"},
            )
            runner = ValuationRunner(settings=self.settings)
            result = runner.run(request)
            memo_result = self._generate_memo(
                request=request,
                result=result,
                runner=runner,
            )
            company_name = self._resolve_company_name(
                runner=runner,
                spreadsheet_id=result.spreadsheet_id,
            )
            spreadsheet_url = _build_google_sheet_url(result.spreadsheet_id)

            if (
                str(result.status).upper() == "COMPLETED"
                and memo_result.status == "COMPLETED"
                and memo_result.pdf_path
            ):
                self.store.mark_completed(
                    execution_id=execution.id,
                    company_name=company_name,
                    spreadsheet_id=result.spreadsheet_id,
                    spreadsheet_url=spreadsheet_url,
                    memo_pdf_path=str(memo_result.pdf_path),
                )
                self._logger.info(
                    "execution_completed execution_id=%s run_id=%s spreadsheet_id=%s",
                    execution.id,
                    execution.run_id,
                    result.spreadsheet_id,
                )
                return

            error_message = self._build_failure_message(result=result, memo_result=memo_result)
            self.store.mark_failed(
                execution_id=execution.id,
                company_name=company_name,
                spreadsheet_id=result.spreadsheet_id if result else None,
                spreadsheet_url=spreadsheet_url,
                memo_pdf_path=str(memo_result.pdf_path) if memo_result and memo_result.pdf_path else None,
                error_message=error_message,
            )
            self._logger.error(
                "execution_failed_non_exception execution_id=%s run_id=%s error=%s",
                execution.id,
                execution.run_id,
                error_message,
            )
        except Exception as exc:  # noqa: BLE001
            spreadsheet_id = result.spreadsheet_id if result else None
            spreadsheet_url = _build_google_sheet_url(spreadsheet_id)
            memo_pdf_path = str(memo_result.pdf_path) if memo_result and memo_result.pdf_path else None
            self.store.mark_failed(
                execution_id=execution.id,
                company_name=None,
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=spreadsheet_url,
                memo_pdf_path=memo_pdf_path,
                error_message=str(exc),
            )
            self._logger.exception(
                "execution_failed_exception execution_id=%s run_id=%s",
                execution.id,
                execution.run_id,
            )

    def _generate_memo(
        self,
        *,
        request: ValuationRunRequest,
        result: ValuationRunResult,
        runner: ValuationRunner,
    ) -> MemoWrapperResult:
        if (
            runner.llm_client is None
            or runner.sheets_engine is None
            or runner.data_service is None
            or runner.research_service is None
        ):
            raise RuntimeError("Runner dependencies missing for post-run memo stage.")
        memo_service = PostRunMemoService(
            settings=self.settings,
            llm_client=runner.llm_client,
            sheets_engine=runner.sheets_engine,
            data_service=runner.data_service,
            research_service=runner.research_service,
            repo_root=self.repo_root,
        )
        return memo_service.generate(
            request=request,
            result=result,
            with_memo=True,
        )

    def _resolve_company_name(
        self,
        *,
        runner: ValuationRunner,
        spreadsheet_id: str | None,
    ) -> str | None:
        if runner.sheets_engine is None or not spreadsheet_id:
            return None
        try:
            values = runner.sheets_engine.read_named_ranges(
                spreadsheet_id,
                ["inp_name"],
                value_render_option="FORMATTED_VALUE",
            )
        except Exception:  # noqa: BLE001
            self._logger.exception(
                "execution_company_name_lookup_failed spreadsheet_id=%s",
                spreadsheet_id,
            )
            return None
        name = _first_sheet_cell(values.get("inp_name"))
        return name or None

    def _normalize_ticker(self, ticker: str | None) -> str:
        normalized = str(ticker or "").strip().upper()
        if not normalized:
            raise ValueError("Ticker is required.")
        if not _TICKER_RE.fullmatch(normalized):
            raise ValueError(
                "Ticker must match pattern ^[A-Z][A-Z0-9.\\-]{0,9}$."
            )
        return normalized

    def _normalize_status(self, status: str) -> str:
        normalized = str(status).strip().upper()
        if normalized not in {"QUEUED", "RUNNING", "COMPLETED", "FAILED"}:
            raise ValueError("status must be one of QUEUED, RUNNING, COMPLETED, FAILED.")
        return normalized

    def _build_failure_message(
        self,
        *,
        result: ValuationRunResult | None,
        memo_result: MemoWrapperResult | None,
    ) -> str:
        parts: list[str] = []
        if result is not None:
            parts.append(f"valuation_status={result.status}")
            if result.notes:
                parts.append(f"valuation_notes={result.notes}")
        if memo_result is not None:
            parts.append(f"memo_status={memo_result.status}")
            if memo_result.notes:
                parts.append("memo_notes=" + "; ".join(memo_result.notes))
        return " | ".join(parts) if parts else "Execution failed with unknown error."


def _build_google_sheet_url(spreadsheet_id: str | None) -> str | None:
    normalized = str(spreadsheet_id or "").strip()
    if not normalized:
        return None
    return f"https://docs.google.com/spreadsheets/d/{normalized}/edit"


def _first_sheet_cell(value: Any) -> str:
    current = value
    while isinstance(current, list) and len(current) == 1:
        current = current[0]
    if current is None:
        return ""
    if isinstance(current, list):
        if not current:
            return ""
        return str(current[0]).strip()
    return str(current).strip()
