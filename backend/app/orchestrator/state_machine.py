"""Phase-v1 workflow state machine for valuation runs."""

from __future__ import annotations

from enum import Enum


class WorkflowPhase(str, Enum):
    """Deterministic orchestration phases for the multi-turn run."""

    INTAKE = "intake"
    DATA_COLLECTION = "data_collection"
    DATA_QUALITY_CHECKS = "data_quality_checks"
    ASSUMPTIONS = "assumptions"
    MODEL_RUN = "model_run"
    VALIDATION = "validation"
    MEMO = "memo"
    PUBLISH = "publish"


class V1WorkflowStateMachine:
    """Ordered phase transitions for phase-v1 orchestration."""

    _ORDER: tuple[WorkflowPhase, ...] = (
        WorkflowPhase.INTAKE,
        WorkflowPhase.DATA_COLLECTION,
        WorkflowPhase.DATA_QUALITY_CHECKS,
        WorkflowPhase.ASSUMPTIONS,
        WorkflowPhase.MODEL_RUN,
        WorkflowPhase.VALIDATION,
        WorkflowPhase.MEMO,
        WorkflowPhase.PUBLISH,
    )

    def ordered_phases(self) -> tuple[WorkflowPhase, ...]:
        """Return canonical execution order for the workflow."""
        return self._ORDER

    def next_phase(self, current: WorkflowPhase) -> WorkflowPhase | None:
        """Return the next phase, or ``None`` when current is final."""
        try:
            idx = self._ORDER.index(current)
        except ValueError:
            raise KeyError(f"Unknown workflow phase: {current}") from None

        if idx == len(self._ORDER) - 1:
            return None
        return self._ORDER[idx + 1]
