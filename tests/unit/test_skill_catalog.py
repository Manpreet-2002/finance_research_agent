"""Skill catalog integrity tests."""

from __future__ import annotations

from pathlib import Path

from backend.app.orchestrator.state_machine import WorkflowPhase
from backend.app.skills.catalog import PHASE_V1_SKILLS, skill_ids
from backend.app.skills.router import SkillRouter
from backend.app.workbook.inspection import inspect_local_workbook

GOOGLE_TEMPLATE_ONLY_RANGES = {
    "comps_firstrow",
    "comps_table_full",
    "comps_multiples_header",
    "comps_multiples_values",
    "comps_method_note",
    "comps_peer_count",
    "comps_multiple_count",
    "sources_header",
    "sources_firstrow",
    "sources_table",
    "log_actions_table",
    "log_assumptions_table",
    "log_story_table",
    "checks_statuses",
    "story_core_narrative_rows",
    "story_linked_operating_driver_rows",
    "story_kpi_to_track_rows",
}


def test_phase_v1_skill_count_and_uniqueness() -> None:
    ids = skill_ids()
    assert len(ids) == 16
    assert len(set(ids)) == len(ids)


def test_phase_v1_skill_artifacts_exist() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for skill in PHASE_V1_SKILLS:
        skill_dir = repo_root / skill.skill_path
        assert skill_dir.exists()
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "agents" / "openai.yaml").exists()


def test_router_returns_phase_skill_paths() -> None:
    router = SkillRouter()
    paths = router.route_skill_paths_for_phase(WorkflowPhase.INTAKE)
    assert paths == (
        "skills/google-sheets-range-discipline",
        "skills/ticker-intake-and-mandate",
    )


def test_router_includes_data_quality_skill_for_data_quality_phase() -> None:
    router = SkillRouter()
    paths = router.route_skill_paths_for_phase(WorkflowPhase.DATA_QUALITY_CHECKS)
    assert "skills/google-sheets-range-discipline" in paths
    assert "skills/data-quality-gate-and-normalization" in paths


def test_skill_named_ranges_exist_in_template() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    inspection = inspect_local_workbook(
        repo_root / "Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx"
    )
    valid_ranges = set(inspection.named_ranges)
    missing: list[tuple[str, str]] = []
    for skill in PHASE_V1_SKILLS:
        for range_name in skill.named_ranges:
            if range_name not in valid_ranges:
                if range_name in GOOGLE_TEMPLATE_ONLY_RANGES:
                    continue
                missing.append((skill.skill_id, range_name))
    assert not missing


def test_peer_skill_requires_fundamentals_tooling() -> None:
    peer_skill = next(
        skill
        for skill in PHASE_V1_SKILLS
        if skill.skill_id == "peer-set-and-competitive-analysis"
    )
    assert "finnhub_fundamentals" in peer_skill.required_tools
