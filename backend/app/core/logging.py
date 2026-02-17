"""Run-scoped logging helpers for orchestration diagnostics."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_run_logger(run_id: str) -> tuple[logging.Logger, logging.Handler, Path]:
    """Create and attach a file handler for a specific run id."""
    logs_dir = Path("artifacts") / "run_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{run_id}.log"

    logger = logging.getLogger("finance_research_agent")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    if not logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    logger.addHandler(file_handler)
    return logger, file_handler, log_path


def teardown_run_logger(logger: logging.Logger, handler: logging.Handler) -> None:
    """Detach and close a run-scoped handler."""
    logger.removeHandler(handler)
    handler.close()
