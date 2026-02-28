"""Unit tests for execution API routes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient

from backend.app.api.main import create_app
from backend.app.api.executions.service import ExecutionService, ExecutionServiceConfig
from backend.app.api.executions.store import ExecutionStore
from backend.app.core.settings import Settings, load_settings


def _build_test_settings(tmp_path: Path) -> Settings:
    base = load_settings()
    return replace(
        base,
        execution_db_path=str(tmp_path / "executions.db"),
        execution_worker_enabled=False,
        api_cors_origins="",
    )


def test_submit_list_and_get_execution(tmp_path: Path) -> None:
    settings = _build_test_settings(tmp_path)
    app = create_app(settings=settings, start_worker=False, repo_root=tmp_path)

    with TestClient(app) as client:
        submit = client.post("/api/v1/executions", json={"ticker": "aapl"})
        assert submit.status_code == 202
        created = submit.json()
        assert created["ticker"] == "AAPL"
        assert created["status"] == "QUEUED"
        assert created["memo_pdf_url"] is None
        execution_id = created["id"]

        listing = client.get("/api/v1/executions")
        assert listing.status_code == 200
        payload = listing.json()
        assert payload["total"] == 1
        assert payload["items"][0]["id"] == execution_id

        detail = client.get(f"/api/v1/executions/{execution_id}")
        assert detail.status_code == 200
        detail_payload = detail.json()
        assert detail_payload["id"] == execution_id
        assert detail_payload["run_id"] == created["run_id"]
        assert detail_payload["status"] == "QUEUED"


def test_submit_rejects_invalid_ticker(tmp_path: Path) -> None:
    settings = _build_test_settings(tmp_path)
    app = create_app(settings=settings, start_worker=False, repo_root=tmp_path)

    with TestClient(app) as client:
        response = client.post("/api/v1/executions", json={"ticker": "$AAPL"})
        assert response.status_code == 422
        assert "Ticker must match pattern" in response.json()["detail"]


def test_memo_pdf_is_served_through_api(tmp_path: Path) -> None:
    settings = _build_test_settings(tmp_path)
    app = create_app(settings=settings, start_worker=False, repo_root=tmp_path)

    with TestClient(app) as client:
        submit = client.post("/api/v1/executions", json={"ticker": "MSFT"})
        execution_id = submit.json()["id"]
        run_id = submit.json()["run_id"]

        memo_dir = tmp_path / "artifacts" / "memos" / run_id
        memo_dir.mkdir(parents=True, exist_ok=True)
        memo_path = memo_dir / "investment_memo.pdf"
        memo_path.write_bytes(b"%PDF-1.4\n%test\n")

        store = app.state.execution_store
        store.mark_completed(
            execution_id=execution_id,
            company_name="Microsoft Corporation",
            spreadsheet_id="sheet_123",
            spreadsheet_url="https://docs.google.com/spreadsheets/d/sheet_123/edit",
            memo_pdf_path=str(memo_path),
        )

        detail = client.get(f"/api/v1/executions/{execution_id}")
        assert detail.status_code == 200
        memo_url = detail.json()["memo_pdf_url"]
        assert memo_url

        download = client.get(f"/api/v1/executions/{execution_id}/memo.pdf")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/pdf")


def test_memo_pdf_path_outside_allowed_root_is_forbidden(tmp_path: Path) -> None:
    settings = _build_test_settings(tmp_path)
    app = create_app(settings=settings, start_worker=False, repo_root=tmp_path)

    with TestClient(app) as client:
        submit = client.post("/api/v1/executions", json={"ticker": "AMZN"})
        execution_id = submit.json()["id"]

        outside_path = tmp_path / "outside.pdf"
        outside_path.write_bytes(b"%PDF-1.4\n%outside\n")

        store = app.state.execution_store
        store.mark_completed(
            execution_id=execution_id,
            company_name="Amazon.com, Inc.",
            spreadsheet_id="sheet_456",
            spreadsheet_url="https://docs.google.com/spreadsheets/d/sheet_456/edit",
            memo_pdf_path=str(outside_path),
        )

        download = client.get(f"/api/v1/executions/{execution_id}/memo.pdf")
        assert download.status_code == 403


def test_execution_worker_dispatches_runs_on_separate_threads(tmp_path: Path) -> None:
    settings = replace(
        _build_test_settings(tmp_path),
        execution_worker_enabled=True,
    )
    store = ExecutionStore(tmp_path / "executions.db")
    store.initialize()

    release_event = threading.Event()
    started_event = threading.Event()
    thread_names: list[str] = []
    thread_names_lock = threading.Lock()

    class BlockingExecutionService(ExecutionService):
        def _process_claimed_execution(self, execution):  # type: ignore[override]
            with thread_names_lock:
                thread_names.append(threading.current_thread().name)
                if len(thread_names) >= 2:
                    started_event.set()
            release_event.wait(timeout=2)
            self.store.mark_completed(
                execution_id=execution.id,
                company_name=None,
                spreadsheet_id=None,
                spreadsheet_url=None,
                memo_pdf_path=None,
            )

    service = BlockingExecutionService(
        settings=settings,
        store=store,
        config=ExecutionServiceConfig(
            poll_seconds=0.01,
            worker_enabled=True,
            max_workers=2,
        ),
        repo_root=tmp_path,
    )

    try:
        service.start()
        first = service.submit_execution(ticker="AAPL")
        second = service.submit_execution(ticker="MSFT")

        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and not started_event.is_set():
            time.sleep(0.02)

        assert started_event.is_set(), "Expected two executions to dispatch concurrently."
        assert store.get_execution(first.id).status == "RUNNING"
        assert store.get_execution(second.id).status == "RUNNING"
        assert all(name.startswith("execution-runner") for name in thread_names)
        assert "execution-worker" not in thread_names
    finally:
        release_event.set()
        service.shutdown()
