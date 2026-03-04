"""Range parsing/guardrail helpers for Google Sheets engine."""

from __future__ import annotations

from dataclasses import replace

from backend.app.core.settings import load_settings
from backend.app.sheets.google_engine import (
    GoogleSheetsEngine,
    _RangeBounds,
    _coerce_matrix_for_named_range,
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


def test_resolve_named_range_targets_requires_exact_named_range() -> None:
    resolved, missing = _resolve_named_range_targets(
        names=["OUT_WACC"],
        known_ranges={"OUT_WACC", "out_terminal_g"},
    )
    assert missing == []
    assert resolved["OUT_WACC"] == "OUT_WACC"


def test_resolve_named_range_targets_reports_missing_when_no_alias_exists() -> None:
    resolved, missing = _resolve_named_range_targets(
        names=["OUT_WACC"],
        known_ranges={"out_terminal_g"},
    )
    assert resolved == {}
    assert missing == ["OUT_WACC"]


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


def test_coerce_matrix_for_named_range_column_to_row() -> None:
    matrix, mode = _coerce_matrix_for_named_range(
        name="sens_terminal_g_vector",
        matrix=[[0.01], [0.015], [0.02], [0.025], [0.03]],
        target_rows=1,
        target_cols=5,
    )
    assert mode == "column_to_row"
    assert matrix == [[0.01, 0.015, 0.02, 0.025, 0.03]]


def test_coerce_matrix_for_named_range_row_to_column() -> None:
    matrix, mode = _coerce_matrix_for_named_range(
        name="sens_wacc_vector",
        matrix=[[0.085, 0.09, 0.095, 0.1, 0.105]],
        target_rows=5,
        target_cols=1,
    )
    assert mode == "row_to_column"
    assert matrix == [[0.085], [0.09], [0.095], [0.1], [0.105]]


def test_coerce_matrix_for_named_range_vector_length_mismatch_raises() -> None:
    try:
        _coerce_matrix_for_named_range(
            name="sens_wacc_vector",
            matrix=[[0.085, 0.09, 0.095, 0.1]],
            target_rows=5,
            target_cols=1,
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ValueError for vector length mismatch.")
    assert "sens_wacc_vector" in message
    assert "expected 5x1" in message


def test_coerce_matrix_for_named_range_rectangular_requires_exact_shape() -> None:
    try:
        _coerce_matrix_for_named_range(
            name="sens_grid_values",
            matrix=[[1, 2, 3, 4]],
            target_rows=2,
            target_cols=2,
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ValueError for rectangular shape mismatch.")
    assert "sens_grid_values" in message
    assert "expected 2 rows" in message


def test_google_oauth_json_secrets_are_staged_to_runtime_dir(tmp_path) -> None:
    settings = replace(
        load_settings(),
        google_oauth_client_secret_json='{"installed":{"client_id":"abc"}}',
        google_oauth_token_json='{"refresh_token":"token"}',
        google_oauth_runtime_dir=str(tmp_path / "google"),
    )
    engine = GoogleSheetsEngine(settings=settings)

    client_path, token_path = engine._resolve_oauth_file_paths()

    assert client_path == tmp_path / "google" / "credentials.json"
    assert token_path == tmp_path / "google" / "token.json"
    assert client_path.read_text(encoding="utf-8") == '{"installed":{"client_id":"abc"}}'
    assert token_path.read_text(encoding="utf-8") == '{"refresh_token":"token"}'
