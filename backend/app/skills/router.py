"""Skill router for phase-v1 orchestration phases."""

from __future__ import annotations

from dataclasses import dataclass

from ..orchestrator.state_machine import WorkflowPhase
from .catalog import PHASE_V1_SKILLS, SkillSpec


@dataclass
class SkillRouter:
    """Resolve skill execution sets by workflow phase."""

    catalog: tuple[SkillSpec, ...] = PHASE_V1_SKILLS

    def route_for_phase(self, phase: WorkflowPhase) -> tuple[SkillSpec, ...]:
        target_phase = phase.value
        return tuple(
            skill
            for skill in self.catalog
            if skill.phase in (target_phase, "global")
        )

    def route_skill_paths_for_phase(self, phase: WorkflowPhase) -> tuple[str, ...]:
        """Return filesystem skill paths for a workflow phase."""
        return tuple(skill.skill_path for skill in self.route_for_phase(phase))
