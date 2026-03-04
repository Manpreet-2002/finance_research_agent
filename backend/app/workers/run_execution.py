"""CLI entrypoint for processing a single queued/running execution."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from ..api.executions.launcher import NoopExecutionLauncher
from ..api.executions.artifact_store import build_memo_artifact_store
from ..api.executions.service import ExecutionService, ExecutionServiceConfig
from ..api.executions.store_factory import build_execution_store
from ..core.env import load_env_file
from ..core.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a single valuation execution outside the API web process.",
    )
    parser.add_argument(
        "--execution-id",
        default="",
        help="Execution id to process. Falls back to the EXECUTION_ID environment variable.",
    )
    args = parser.parse_args()

    load_env_file()
    settings = load_settings()
    execution_id = str(args.execution_id or "").strip() or str(
        os.environ.get(
            settings.cloud_run_job_execution_env_name.strip() or "EXECUTION_ID",
            "",
        )
    ).strip()
    if not execution_id:
        parser.error("Provide --execution-id or set the configured execution id environment variable.")

    repo_root = Path(__file__).resolve().parents[3]
    store = build_execution_store(
        settings=settings,
        repo_root=repo_root,
    )
    store.initialize()
    service = ExecutionService(
        settings=settings,
        store=store,
        config=ExecutionServiceConfig(
            poll_seconds=settings.execution_worker_poll_seconds,
            worker_enabled=False,
            max_workers=1,
        ),
        repo_root=repo_root,
        launcher=NoopExecutionLauncher(),
        memo_artifact_store=build_memo_artifact_store(settings),
    )
    service.run_execution_by_id(execution_id, allow_queued_claim=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
