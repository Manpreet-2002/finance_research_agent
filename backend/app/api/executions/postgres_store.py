"""PostgreSQL-backed execution persistence for multi-instance deployments."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from .models import ExecutionRecord, ExecutionStatus, VALID_EXECUTION_STATUSES, utc_now_iso

_DISPATCH_ADVISORY_LOCK_KEY = 810_426_001


class PostgresExecutionStore:
    """Persistence layer for execution records stored in PostgreSQL."""

    def __init__(self, database_url: str) -> None:
        self.database_url = str(database_url).strip()
        if not self.database_url:
            raise ValueError("execution_database_url is required for PostgreSQL execution store.")

    def initialize(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
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
                    memo_pdf_external_url TEXT,
                    job_execution_name TEXT,
                    error_message TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_executions_status_submitted
                ON executions(status, submitted_at_utc DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_executions_ticker_submitted
                ON executions(ticker, submitted_at_utc DESC)
                """
            )
            cur.execute(
                """
                ALTER TABLE executions
                ADD COLUMN IF NOT EXISTS memo_pdf_external_url TEXT
                """
            )
            cur.execute(
                """
                ALTER TABLE executions
                ADD COLUMN IF NOT EXISTS job_execution_name TEXT
                """
            )

    def create_execution(self, *, ticker: str) -> ExecutionRecord:
        now = utc_now_iso()
        execution_id = str(uuid4())
        run_id = self._build_run_id()
        with self._connect() as conn, conn.cursor() as cur:
            row = cur.execute(
                """
                INSERT INTO executions (
                    id, run_id, ticker, company_name, status, submitted_at_utc,
                    started_at_utc, finished_at_utc, spreadsheet_id, spreadsheet_url,
                    memo_pdf_path, memo_pdf_external_url, job_execution_name,
                    error_message, created_at_utc, updated_at_utc
                )
                VALUES (
                    %s, %s, %s, NULL, 'QUEUED', %s,
                    NULL, NULL, NULL, NULL,
                    NULL, NULL, NULL, NULL, %s, %s
                )
                RETURNING *
                """,
                (execution_id, run_id, ticker, now, now, now),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to load inserted execution row {execution_id}.")
        return self._row_to_record(row)

    def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        with self._connect() as conn, conn.cursor() as cur:
            row = cur.execute(
                "SELECT * FROM executions WHERE id = %s",
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
            where.append("ticker = %s")
            params.append(ticker)
        if status:
            where.append("status = %s")
            params.append(status)
        if from_utc:
            where.append("submitted_at_utc >= %s")
            params.append(from_utc)
        if to_utc:
            where.append("submitted_at_utc <= %s")
            params.append(to_utc)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self._connect() as conn, conn.cursor() as cur:
            total_row = cur.execute(
                f"SELECT COUNT(*) AS count FROM executions {where_sql}",
                tuple(params),
            ).fetchone()
            rows = cur.execute(
                f"""
                SELECT * FROM executions
                {where_sql}
                ORDER BY submitted_at_utc DESC
                LIMIT %s OFFSET %s
                """,
                (*params, page_size, offset),
            ).fetchall()

        total = int((total_row or {}).get("count", 0))
        return [self._row_to_record(row) for row in rows], total

    def has_running_execution(self) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            row = cur.execute(
                """
                SELECT 1 AS present
                FROM executions
                WHERE status = 'RUNNING'
                LIMIT 1
                """
            ).fetchone()
        return row is not None

    def claim_next_queued(self) -> ExecutionRecord | None:
        now = utc_now_iso()
        with self._connect() as conn, conn.cursor() as cur:
            row = cur.execute(
                """
                SELECT * FROM executions
                WHERE status = 'QUEUED'
                ORDER BY submitted_at_utc ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            ).fetchone()
            if row is None:
                return None
            execution_id = str(row["id"])
            updated = cur.execute(
                """
                UPDATE executions
                SET status = 'RUNNING',
                    started_at_utc = COALESCE(started_at_utc, %s),
                    updated_at_utc = %s,
                    error_message = NULL
                WHERE id = %s
                RETURNING *
                """,
                (now, now, execution_id),
            ).fetchone()
        if updated is None:
            raise RuntimeError(f"Execution {execution_id} disappeared after claim.")
        return self._row_to_record(updated)

    def claim_next_queued_if_none_running(self) -> ExecutionRecord | None:
        now = utc_now_iso()
        with self._connect() as conn, conn.cursor() as cur:
            lock_row = cur.execute(
                "SELECT pg_try_advisory_xact_lock(%s) AS locked",
                (_DISPATCH_ADVISORY_LOCK_KEY,),
            ).fetchone()
            if not lock_row or not bool(lock_row["locked"]):
                return None

            running = cur.execute(
                """
                SELECT 1 AS present
                FROM executions
                WHERE status = 'RUNNING'
                LIMIT 1
                """
            ).fetchone()
            if running is not None:
                return None

            row = cur.execute(
                """
                SELECT * FROM executions
                WHERE status = 'QUEUED'
                ORDER BY submitted_at_utc ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            ).fetchone()
            if row is None:
                return None

            execution_id = str(row["id"])
            updated = cur.execute(
                """
                UPDATE executions
                SET status = 'RUNNING',
                    started_at_utc = COALESCE(started_at_utc, %s),
                    updated_at_utc = %s,
                    error_message = NULL
                WHERE id = %s
                RETURNING *
                """,
                (now, now, execution_id),
            ).fetchone()
        if updated is None:
            raise RuntimeError(f"Execution {execution_id} disappeared after claim.")
        return self._row_to_record(updated)

    def claim_execution_by_id(self, execution_id: str) -> ExecutionRecord | None:
        now = utc_now_iso()
        with self._connect() as conn, conn.cursor() as cur:
            row = cur.execute(
                """
                SELECT * FROM executions
                WHERE id = %s
                FOR UPDATE
                """,
                (execution_id,),
            ).fetchone()
            if row is None:
                return None

            status = str(row["status"])
            if status == "RUNNING":
                return self._row_to_record(row)
            if status != "QUEUED":
                return None

            updated = cur.execute(
                """
                UPDATE executions
                SET status = 'RUNNING',
                    started_at_utc = %s,
                    updated_at_utc = %s,
                    error_message = NULL
                WHERE id = %s
                RETURNING *
                """,
                (now, now, execution_id),
            ).fetchone()
        if updated is None:
            raise RuntimeError(f"Execution {execution_id} disappeared after claim.")
        return self._row_to_record(updated)

    def requeue_execution(self, *, execution_id: str) -> ExecutionRecord:
        now = utc_now_iso()
        with self._connect() as conn, conn.cursor() as cur:
            row = cur.execute(
                """
                UPDATE executions
                SET status = 'QUEUED',
                    started_at_utc = NULL,
                    finished_at_utc = NULL,
                    job_execution_name = NULL,
                    error_message = NULL,
                    updated_at_utc = %s
                WHERE id = %s
                RETURNING *
                """,
                (now, execution_id),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Execution {execution_id} not found when requeueing.")
        return self._row_to_record(row)

    def set_job_execution_name(
        self,
        *,
        execution_id: str,
        job_execution_name: str | None,
    ) -> ExecutionRecord:
        now = utc_now_iso()
        with self._connect() as conn, conn.cursor() as cur:
            row = cur.execute(
                """
                UPDATE executions
                SET job_execution_name = %s,
                    updated_at_utc = %s
                WHERE id = %s
                RETURNING *
                """,
                (job_execution_name, now, execution_id),
            ).fetchone()
        if row is None:
            raise RuntimeError(
                f"Execution {execution_id} not found when saving job execution metadata."
            )
        return self._row_to_record(row)

    def mark_completed(
        self,
        *,
        execution_id: str,
        company_name: str | None,
        spreadsheet_id: str | None,
        spreadsheet_url: str | None,
        memo_pdf_path: str | None,
        memo_pdf_external_url: str | None = None,
    ) -> ExecutionRecord:
        finished = utc_now_iso()
        with self._connect() as conn, conn.cursor() as cur:
            row = cur.execute(
                """
                UPDATE executions
                SET status = 'COMPLETED',
                    company_name = %s,
                    finished_at_utc = %s,
                    spreadsheet_id = %s,
                    spreadsheet_url = %s,
                    memo_pdf_path = %s,
                    memo_pdf_external_url = COALESCE(%s, memo_pdf_external_url),
                    error_message = NULL,
                    updated_at_utc = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    company_name,
                    finished,
                    spreadsheet_id,
                    spreadsheet_url,
                    memo_pdf_path,
                    memo_pdf_external_url,
                    finished,
                    execution_id,
                ),
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
        memo_pdf_external_url: str | None = None,
    ) -> ExecutionRecord:
        finished = utc_now_iso()
        with self._connect() as conn, conn.cursor() as cur:
            row = cur.execute(
                """
                UPDATE executions
                SET status = 'FAILED',
                    company_name = COALESCE(%s, company_name),
                    finished_at_utc = %s,
                    spreadsheet_id = COALESCE(%s, spreadsheet_id),
                    spreadsheet_url = COALESCE(%s, spreadsheet_url),
                    memo_pdf_path = COALESCE(%s, memo_pdf_path),
                    memo_pdf_external_url = COALESCE(%s, memo_pdf_external_url),
                    error_message = %s,
                    updated_at_utc = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    company_name,
                    finished,
                    spreadsheet_id,
                    spreadsheet_url,
                    memo_pdf_path,
                    memo_pdf_external_url,
                    error_message,
                    finished,
                    execution_id,
                ),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Execution {execution_id} not found when marking failed.")
        return self._row_to_record(row)

    def _build_run_id(self) -> str:
        now = utc_now_iso().replace("+00:00", "Z")
        compact = now.replace("-", "").replace(":", "").replace(".", "")
        return f"api_{compact}_{uuid4().hex[:8]}"

    def _connect(self) -> Any:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - exercised only when dependency missing
            raise RuntimeError(
                "PostgreSQL execution store requires psycopg. Run `uv sync` to install it."
            ) from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _row_to_record(self, row: dict[str, Any]) -> ExecutionRecord:
        status = str(row["status"])
        if status not in VALID_EXECUTION_STATUSES:
            raise RuntimeError(f"Invalid execution status in DB: {status}")
        return ExecutionRecord(
            id=str(row["id"]),
            run_id=str(row["run_id"]),
            ticker=str(row["ticker"]),
            company_name=_as_optional_text(row.get("company_name")),
            status=status,  # type: ignore[arg-type]
            submitted_at_utc=str(row["submitted_at_utc"]),
            started_at_utc=_as_optional_text(row.get("started_at_utc")),
            finished_at_utc=_as_optional_text(row.get("finished_at_utc")),
            spreadsheet_id=_as_optional_text(row.get("spreadsheet_id")),
            spreadsheet_url=_as_optional_text(row.get("spreadsheet_url")),
            memo_pdf_path=_as_optional_text(row.get("memo_pdf_path")),
            memo_pdf_external_url=_as_optional_text(row.get("memo_pdf_external_url")),
            job_execution_name=_as_optional_text(row.get("job_execution_name")),
            error_message=_as_optional_text(row.get("error_message")),
            created_at_utc=str(row["created_at_utc"]),
            updated_at_utc=str(row["updated_at_utc"]),
        )


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
