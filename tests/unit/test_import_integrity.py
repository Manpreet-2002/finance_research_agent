"""Import-order regression checks."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def _run_python(code: str) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONPATH"] = "."
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_import_skills_catalog_in_fresh_process() -> None:
    result = _run_python(
        "from backend.app.skills.catalog import PHASE_V1_SKILLS; "
        "print(len(PHASE_V1_SKILLS))"
    )
    assert result.returncode == 0, result.stderr


def test_import_skills_catalog_after_orchestrator_state_machine() -> None:
    result = _run_python(
        "from backend.app.orchestrator.state_machine import WorkflowPhase; "
        "from backend.app.skills.catalog import PHASE_V1_SKILLS; "
        "print(WorkflowPhase.INTAKE.value, len(PHASE_V1_SKILLS))"
    )
    assert result.returncode == 0, result.stderr
