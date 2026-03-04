"""Execution store factory for local and Cloud Run deployments."""

from __future__ import annotations

from pathlib import Path

from ...core.settings import Settings
from .postgres_store import PostgresExecutionStore
from .store import ExecutionStore


def build_execution_store(*, settings: Settings, repo_root: Path) -> ExecutionStore | PostgresExecutionStore:
    """Build the configured execution store implementation."""

    backend = str(settings.execution_store_backend).strip().lower()
    database_url = str(settings.execution_database_url).strip()
    if backend == "postgres" or database_url.startswith(("postgres://", "postgresql://")):
        if not database_url:
            raise RuntimeError(
                "EXECUTION_DATABASE_URL is required when EXECUTION_STORE_BACKEND=postgres."
            )
        return PostgresExecutionStore(database_url=database_url)

    db_path = Path(settings.execution_db_path)
    if not db_path.is_absolute():
        db_path = repo_root / db_path
    return ExecutionStore(db_path=db_path)
