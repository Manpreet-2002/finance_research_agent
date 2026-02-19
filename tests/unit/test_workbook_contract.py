"""Workbook contract regression tests for phase-v1 named-range requirements."""

from __future__ import annotations

from backend.app.workbook.contract import PHASE_V1_REQUIRED_NAMED_RANGE_PATTERNS


def test_phase_v1_contract_requires_dynamic_comps_and_table_ranges() -> None:
    required = set(PHASE_V1_REQUIRED_NAMED_RANGE_PATTERNS)
    assert "comps_firstrow" in required
    assert "comps_table_full" in required
    assert "comps_multiples_header" in required
    assert "comps_multiples_values" in required
    assert "comps_method_note" in required
    assert "comps_peer_count" in required
    assert "comps_multiple_count" in required
    assert "sources_header" in required
    assert "sources_firstrow" in required
    assert "sources_table" in required
    assert "log_actions_table" in required
    assert "log_assumptions_table" in required
    assert "log_story_table" in required
    assert "checks_statuses" in required
    assert "story_core_narrative_rows" in required
    assert "story_linked_operating_driver_rows" in required
    assert "story_kpi_to_track_rows" in required
