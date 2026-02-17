"""Range parsing/guardrail helpers for Google Sheets engine."""

from __future__ import annotations

from backend.app.sheets.google_engine import (
    _RangeBounds,
    _first_empty_row_offset,
    _is_formula_owned_name,
    _overlaps_formula_owned,
    _parse_a1_range,
    _resolve_named_range_targets,
)


def test_parse_a1_range_accepts_quoted_sheet_names() -> None:
    parsed = _parse_a1_range("'Agent Log'!B17:J17")

    assert parsed is not None
    assert parsed.sheet == "Agent Log"
    assert parsed.col_start == 2
    assert parsed.col_end == 10
    assert parsed.row_start == 17
    assert parsed.row_end == 17


def test_parse_a1_range_rejects_invalid_tokens() -> None:
    assert _parse_a1_range("Sources_A1") is None
    assert _parse_a1_range("'Sources!A2'") is None
    assert _parse_a1_range("Inputs!inp_rev_hist_last") is None


def test_formula_overlap_detection() -> None:
    candidate = _parse_a1_range("Output!C6")
    protected = (
        _RangeBounds(
            sheet="Output",
            row_start=6,
            row_end=6,
            col_start=3,
            col_end=3,
        ),
    )

    assert candidate is not None
    assert _overlaps_formula_owned(candidate, protected) is True


def test_formula_owned_named_range_detection() -> None:
    assert _is_formula_owned_name("out_value_ps_weighted")
    assert _is_formula_owned_name("calc_wacc")
    assert not _is_formula_owned_name("inp_base_wacc")


def test_resolve_named_range_targets_supports_output_alias() -> None:
    resolved, missing = _resolve_named_range_targets(
        names=["out_wacc"],
        known_ranges={"OUT_WACC", "out_terminal_g"},
    )
    assert missing == []
    assert resolved["out_wacc"] == "OUT_WACC"


def test_resolve_named_range_targets_reports_missing_when_no_alias_exists() -> None:
    resolved, missing = _resolve_named_range_targets(
        names=["out_wacc"],
        known_ranges={"out_terminal_g"},
    )
    assert resolved == {}
    assert missing == ["out_wacc"]


def test_first_empty_row_offset_handles_prefilled_index_rows() -> None:
    values = [[1], [2], [3]]
    assert _first_empty_row_offset(values, width=3, max_rows=3) is None
    assert (
        _first_empty_row_offset(
            values,
            width=3,
            max_rows=3,
            allow_prefilled_index_column=True,
        )
        == 0
    )
