"""Unit tests for execution API routes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient

from backend.app.api.main import create_app
from backend.app.api.executions.launcher import ExecutionLaunchResult
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


def test_submit_auto_dispatches_via_launcher_when_external_mode(tmp_path: Path) -> None:
    settings = replace(
        _build_test_settings(tmp_path),
        execution_dispatch_mode="cloud_run_job",
        execution_worker_enabled=False,
    )
    store = ExecutionStore(tmp_path / "executions.db")

    launched_execution_ids: list[str] = []

    class FakeLauncher:
        def launch(self, execution):  # type: ignore[no-untyped-def]
            launched_execution_ids.append(execution.id)
            return ExecutionLaunchResult(job_execution_name="operations/dispatch-001")

    service = ExecutionService(
        settings=settings,
        store=store,
        config=ExecutionServiceConfig(
            poll_seconds=0.01,
            worker_enabled=False,
            max_workers=1,
        ),
        repo_root=tmp_path,
        launcher=FakeLauncher(),
    )
    app = create_app(
        settings=settings,
        execution_service=service,
        start_worker=False,
        repo_root=tmp_path,
    )

    with TestClient(app) as client:
        submit = client.post("/api/v1/executions", json={"ticker": "aapl"})
        assert submit.status_code == 202
        payload = submit.json()
        assert payload["status"] == "RUNNING"
        assert launched_execution_ids == [payload["id"]]

        record = store.get_execution(payload["id"])
        assert record is not None
        assert record.status == "RUNNING"
        assert record.job_execution_name == "operations/dispatch-001"

        second_submit = client.post("/api/v1/executions", json={"ticker": "msft"})
        assert second_submit.status_code == 202
        second_payload = second_submit.json()
        assert second_payload["status"] == "QUEUED"
        assert launched_execution_ids == [payload["id"]]


def test_internal_dispatch_endpoint_requires_token_and_dispatches(tmp_path: Path) -> None:
    settings = replace(
        _build_test_settings(tmp_path),
        execution_dispatch_mode="cloud_run_job",
        execution_worker_enabled=False,
        execution_internal_auth_token="dispatch-secret",
    )
    store = ExecutionStore(tmp_path / "executions.db")

    launched_execution_ids: list[str] = []

    class FakeLauncher:
        def launch(self, execution):  # type: ignore[no-untyped-def]
            launched_execution_ids.append(execution.id)
            return ExecutionLaunchResult(job_execution_name="operations/dispatch-002")

    service = ExecutionService(
        settings=settings,
        store=store,
        config=ExecutionServiceConfig(
            poll_seconds=0.01,
            worker_enabled=False,
            max_workers=1,
        ),
        repo_root=tmp_path,
        launcher=FakeLauncher(),
    )
    app = create_app(
        settings=settings,
        execution_service=service,
        start_worker=False,
        repo_root=tmp_path,
    )

    with TestClient(app) as client:
        execution = app.state.execution_store.create_execution(ticker="MSFT")

        unauthorized = client.post("/api/v1/internal/dispatch-next")
        assert unauthorized.status_code == 401

        authorized = client.post(
            "/api/v1/internal/dispatch-next",
            headers={"Authorization": "Bearer dispatch-secret"},
        )
        assert authorized.status_code == 200
        payload = authorized.json()
        assert payload["dispatched"] is True
        assert payload["execution"]["id"] == execution.id
        assert payload["execution"]["status"] == "RUNNING"
        assert launched_execution_ids == [execution.id]


def test_external_memo_url_is_exposed_without_local_file(tmp_path: Path) -> None:
    settings = _build_test_settings(tmp_path)
    app = create_app(settings=settings, start_worker=False, repo_root=tmp_path)

    with TestClient(app) as client:
        submit = client.post("/api/v1/executions", json={"ticker": "NVDA"})
        execution_id = submit.json()["id"]

        store = app.state.execution_store
        store.mark_completed(
            execution_id=execution_id,
            company_name="NVIDIA Corporation",
            spreadsheet_id="sheet_999",
            spreadsheet_url="https://docs.google.com/spreadsheets/d/sheet_999/edit",
            memo_pdf_path=None,
            memo_pdf_external_url="https://storage.googleapis.com/example-bucket/memos/nvda.pdf",
        )

        detail = client.get(f"/api/v1/executions/{execution_id}")
        assert detail.status_code == 200
        assert detail.json()["memo_pdf_url"].endswith(f"/api/v1/executions/{execution_id}/memo.pdf")

        download = client.get(
            f"/api/v1/executions/{execution_id}/memo.pdf",
            follow_redirects=False,
        )
        assert download.status_code == 307
        assert (
            download.headers["location"]
            == "https://storage.googleapis.com/example-bucket/memos/nvda.pdf"
        )


def test_gcs_memo_reference_is_streamed_through_api(tmp_path: Path) -> None:
    settings = _build_test_settings(tmp_path)

    class FakeMemoArtifactStore:
        def publish(self, *, run_id, memo_result):  # type: ignore[no-untyped-def]  # pragma: no cover
            raise NotImplementedError

        def download(self, reference):  # type: ignore[no-untyped-def]
            assert reference == "gs://finance-bucket/memos/demo.pdf"
            from backend.app.api.executions.artifact_store import DownloadedMemoArtifact

            return DownloadedMemoArtifact(
                content=b"%PDF-1.4\n%from-gcs\n",
                media_type="application/pdf",
            )

    app = create_app(
        settings=settings,
        memo_artifact_store=FakeMemoArtifactStore(),
        start_worker=False,
        repo_root=tmp_path,
    )

    with TestClient(app) as client:
        submit = client.post("/api/v1/executions", json={"ticker": "GOOG"})
        execution_id = submit.json()["id"]

        store = app.state.execution_store
        store.mark_completed(
            execution_id=execution_id,
            company_name="Alphabet Inc.",
            spreadsheet_id="sheet_777",
            spreadsheet_url="https://docs.google.com/spreadsheets/d/sheet_777/edit",
            memo_pdf_path=None,
            memo_pdf_external_url="gs://finance-bucket/memos/demo.pdf",
        )

        detail = client.get(f"/api/v1/executions/{execution_id}")
        assert detail.status_code == 200
        assert detail.json()["memo_pdf_url"].endswith(f"/api/v1/executions/{execution_id}/memo.pdf")

        download = client.get(f"/api/v1/executions/{execution_id}/memo.pdf")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/pdf")
        assert download.content.startswith(b"%PDF-1.4")


def test_memo_pdf_url_uses_forwarded_https_scheme(tmp_path: Path) -> None:
    settings = _build_test_settings(tmp_path)
    app = create_app(settings=settings, start_worker=False, repo_root=tmp_path)

    with TestClient(app) as client:
        submit = client.post("/api/v1/executions", json={"ticker": "CRM"})
        execution_id = submit.json()["id"]
        run_id = submit.json()["run_id"]

        memo_dir = tmp_path / "artifacts" / "memos" / run_id
        memo_dir.mkdir(parents=True, exist_ok=True)
        memo_path = memo_dir / "investment_memo.pdf"
        memo_path.write_bytes(b"%PDF-1.4\n%test\n")

        store = app.state.execution_store
        store.mark_completed(
            execution_id=execution_id,
            company_name="Salesforce, Inc.",
            spreadsheet_id="sheet_321",
            spreadsheet_url="https://docs.google.com/spreadsheets/d/sheet_321/edit",
            memo_pdf_path=str(memo_path),
        )

        detail = client.get(
            f"/api/v1/executions/{execution_id}",
            headers={"X-Forwarded-Proto": "https"},
        )
        assert detail.status_code == 200
        assert detail.json()["memo_pdf_url"].startswith("https://")


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
