"""FastAPI entrypoint for valuation execution APIs."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..core.env import load_env_file
from ..core.settings import Settings, load_settings
from .executions.router import router as executions_router
from .executions.service import ExecutionService, ExecutionServiceConfig
from .executions.store import ExecutionStore


def create_app(
    *,
    settings: Settings | None = None,
    execution_store: ExecutionStore | None = None,
    execution_service: ExecutionService | None = None,
    start_worker: bool = True,
    repo_root: Path | None = None,
) -> FastAPI:
    load_env_file()
    resolved_settings = settings or load_settings()
    resolved_repo_root = repo_root or Path(__file__).resolve().parents[3]

    db_path = Path(resolved_settings.execution_db_path)
    if not db_path.is_absolute():
        db_path = resolved_repo_root / db_path

    store = execution_store or ExecutionStore(db_path=db_path)
    service = execution_service or ExecutionService(
        settings=resolved_settings,
        store=store,
        config=ExecutionServiceConfig(
            poll_seconds=resolved_settings.execution_worker_poll_seconds,
            worker_enabled=bool(resolved_settings.execution_worker_enabled),
            max_workers=max(1, resolved_settings.execution_worker_concurrency),
        ),
        repo_root=resolved_repo_root,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        store.initialize()
        if start_worker:
            service.start()
        try:
            yield
        finally:
            service.shutdown()

    app = FastAPI(
        title="Finance Research Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.execution_store = store
    app.state.execution_service = service
    app.state.repo_root = resolved_repo_root

    origins = _parse_cors_origins(resolved_settings.api_cors_origins)
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict[str, Any]:
        return {"status": "ok"}

    app.include_router(executions_router)
    return app


def _parse_cors_origins(raw: str) -> list[str]:
    return [item.strip() for item in str(raw).split(",") if item.strip()]


app = create_app()
