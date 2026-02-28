"""SQLite persistence for valuation executions."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from .models import ExecutionRecord, ExecutionStatus, VALID_EXECUTION_STATUSES, utc_now_iso


class ExecutionStore:
    """Persistence layer for queued/running/completed execution records."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    ticker TEXT NOT NULL,
                    company_name TEXT,
                    status TEXT NOT NULL CHECK (status IN ('QUEUED','RUNNING','COMPLETED','FAILED')),
                    submitted_at_utc TEXT NOT NULL,
                    started_at_utc TEXT,
                    finished_at_utc TEXT,
                    spreadsheet_id TEXT,
                    spreadsheet_url TEXT,
                    memo_pdf_path TEXT,
                    error_message TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_executions_status_submitted
                ON executions(status, submitted_at_utc DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_executions_ticker_submitted
                ON executions(ticker, submitted_at_utc DESC)
                """
            )

    def create_execution(self, *, ticker: str) -> ExecutionRecord:
        now = utc_now_iso()
        execution_id = str(uuid4())
        run_id = self._build_run_id()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO executions (
                    id, run_id, ticker, company_name, status, submitted_at_utc,
                    started_at_utc, finished_at_utc, spreadsheet_id, spreadsheet_url,
                    memo_pdf_path, error_message, created_at_utc, updated_at_utc
                )
                VALUES (?, ?, ?, NULL, 'QUEUED', ?, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?)
                """,
                (execution_id, run_id, ticker, now, now, now),
            )
            row = conn.execute(
                "SELECT * FROM executions WHERE id = ?",
                (execution_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to load inserted execution row {execution_id}.")
        return self._row_to_record(row)

    def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM executions WHERE id = ?",
                (execution_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_executions(
        self,
        *,
        page: int,
        page_size: int,
        ticker: str | None = None,
        status: ExecutionStatus | None = None,
        from_utc: str | None = None,
        to_utc: str | None = None,
    ) -> tuple[list[ExecutionRecord], int]:
        offset = (page - 1) * page_size
        where: list[str] = []
        params: list[Any] = []

        if ticker:
            where.append("ticker = ?")
            params.append(ticker)
        if status:
            where.append("status = ?")
            params.append(status)
        if from_utc:
            where.append("submitted_at_utc >= ?")
            params.append(from_utc)
        if to_utc:
            where.append("submitted_at_utc <= ?")
            params.append(to_utc)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self._connect() as conn:
            total_row = conn.execute(
                f"SELECT COUNT(*) AS count FROM executions {where_sql}",
                tuple(params),
            ).fetchone()
            rows = conn.execute(
                f"""
                SELECT * FROM executions
                {where_sql}
                ORDER BY submitted_at_utc DESC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, offset),
            ).fetchall()

        total = int(total_row["count"] if total_row is not None else 0)
        return [self._row_to_record(row) for row in rows], total

    def claim_next_queued(self) -> ExecutionRecord | None:
        now = utc_now_iso()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM executions
                WHERE status = 'QUEUED'
                ORDER BY submitted_at_utc ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                conn.commit()
                return None

            execution_id = str(row["id"])
            conn.execute(
                """
                UPDATE executions
                SET status = 'RUNNING',
                    started_at_utc = COALESCE(started_at_utc, ?),
                    updated_at_utc = ?
                WHERE id = ?
                """,
                (now, now, execution_id),
            )
            updated = conn.execute(
                "SELECT * FROM executions WHERE id = ?",
                (execution_id,),
            ).fetchone()
            conn.commit()
            if updated is None:
                raise RuntimeError(f"Execution {execution_id} disappeared after claim.")
            return self._row_to_record(updated)
        finally:
            conn.close()

    def mark_completed(
        self,
        *,
        execution_id: str,
        company_name: str | None,
        spreadsheet_id: str | None,
        spreadsheet_url: str | None,
        memo_pdf_path: str | None,
    ) -> ExecutionRecord:
        finished = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE executions
                SET status = 'COMPLETED',
                    company_name = ?,
                    finished_at_utc = ?,
                    spreadsheet_id = ?,
                    spreadsheet_url = ?,
                    memo_pdf_path = ?,
                    error_message = NULL,
                    updated_at_utc = ?
                WHERE id = ?
                """,
                (
                    company_name,
                    finished,
                    spreadsheet_id,
                    spreadsheet_url,
                    memo_pdf_path,
                    finished,
                    execution_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM executions WHERE id = ?",
                (execution_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Execution {execution_id} not found when marking complete.")
        return self._row_to_record(row)

    def mark_failed(
        self,
        *,
        execution_id: str,
        error_message: str,
        company_name: str | None = None,
        spreadsheet_id: str | None = None,
        spreadsheet_url: str | None = None,
        memo_pdf_path: str | None = None,
    ) -> ExecutionRecord:
        finished = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE executions
                SET status = 'FAILED',
                    company_name = COALESCE(?, company_name),
                    finished_at_utc = ?,
                    spreadsheet_id = COALESCE(?, spreadsheet_id),
                    spreadsheet_url = COALESCE(?, spreadsheet_url),
                    memo_pdf_path = COALESCE(?, memo_pdf_path),
                    error_message = ?,
                    updated_at_utc = ?
                WHERE id = ?
                """,
                (
                    company_name,
                    finished,
                    spreadsheet_id,
                    spreadsheet_url,
                    memo_pdf_path,
                    error_message,
                    finished,
                    execution_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM executions WHERE id = ?",
                (execution_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Execution {execution_id} not found when marking failed.")
        return self._row_to_record(row)

    def _build_run_id(self) -> str:
        now = utc_now_iso().replace("+00:00", "Z")
        compact = (
            now.replace("-", "")
            .replace(":", "")
            .replace(".", "")
        )
        return f"api_{compact}_{uuid4().hex[:8]}"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _row_to_record(self, row: sqlite3.Row) -> ExecutionRecord:
        status = str(row["status"])
        if status not in VALID_EXECUTION_STATUSES:
            raise RuntimeError(f"Invalid execution status in DB: {status}")
        return ExecutionRecord(
            id=str(row["id"]),
            run_id=str(row["run_id"]),
            ticker=str(row["ticker"]),
            company_name=_as_optional_text(row["company_name"]),
            status=status,  # type: ignore[arg-type]
            submitted_at_utc=str(row["submitted_at_utc"]),
            started_at_utc=_as_optional_text(row["started_at_utc"]),
            finished_at_utc=_as_optional_text(row["finished_at_utc"]),
            spreadsheet_id=_as_optional_text(row["spreadsheet_id"]),
            spreadsheet_url=_as_optional_text(row["spreadsheet_url"]),
            memo_pdf_path=_as_optional_text(row["memo_pdf_path"]),
            error_message=_as_optional_text(row["error_message"]),
            created_at_utc=str(row["created_at_utc"]),
            updated_at_utc=str(row["updated_at_utc"]),
        )


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
