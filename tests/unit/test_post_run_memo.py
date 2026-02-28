"""Unit coverage for post-run memo helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone

from backend.app.memo.post_run_memo import (
    _count_valid_peer_revenue_ebit_rows,
    _extract_json_dict,
    _extract_timestamp,
    _flatten_numeric_vector,
    _json_dumps,
    _markdown_to_html_blocks,
    _median_numeric,
    _normalize_citations,
    _scale_to_billions,
    _scalar_float,
    _timestamp_distance_seconds,
)


def test_extract_json_dict_parses_embedded_payload() -> None:
    payload = "prefix {\"memo_title\":\"A\",\"sections\":[]} suffix"
    parsed = _extract_json_dict(payload)
    assert parsed["memo_title"] == "A"


def test_flatten_numeric_vector_handles_matrix_rows() -> None:
    value = [[0.07], ["0.08"], ["9%"], [None]]
    flattened = _flatten_numeric_vector(value)
    assert flattened == [0.07, 0.08, 9.0]


def test_scalar_float_unwraps_nested_matrix() -> None:
    assert _scalar_float([["239.51"]]) == 239.51


def test_timestamp_distance_seconds_uses_absolute_distance() -> None:
    anchor = datetime(2026, 2, 24, 10, 0, 0, tzinfo=timezone.utc)
    target = _extract_timestamp("smoke_20260224T095500Z")
    assert target is not None
    assert _timestamp_distance_seconds(anchor, target) == 300.0


def test_median_numeric_returns_even_and_odd() -> None:
    assert _median_numeric([1, 3, 2]) == 2.0
    assert _median_numeric([1, 4, 2, 3]) == 2.5


def test_scale_to_billions_handles_dollar_and_million_scales() -> None:
    assert _scale_to_billions(135_322_000_000.0) == 135.322
    assert _scale_to_billions(2_500_000_000.0) == 2.5


def test_count_valid_peer_revenue_ebit_rows_filters_invalid_points() -> None:
    rows = [
        {"Revenue ($B)": 10.0, "EBIT ($B)": 3.0},
        {"Revenue ($B)": 0.0, "EBIT ($B)": 1.0},
        {"Revenue ($B)": 4.5, "EBIT ($B)": float("nan")},
        {"Revenue ($B)": "7.2", "EBIT ($B)": "-0.2"},
    ]
    assert _count_valid_peer_revenue_ebit_rows(rows) == 2


def test_normalize_citations_clamps_invalid_indices() -> None:
    text = "Point A [0], point B [12], point C [3]."
    normalized = _normalize_citations(text, max_source_index=5)
    assert normalized == "Point A [1], point B [5], point C [3]."


def test_markdown_to_html_blocks_supports_lists() -> None:
    md = "Intro line.\n\n- one\n- two\n\n1. alpha\n2. beta"
    html = _markdown_to_html_blocks(md)
    assert "<p>Intro line.</p>" in html
    assert "<ul><li>one</li><li>two</li></ul>" in html
    assert "<ol><li>alpha</li><li>beta</li></ol>" in html


def test_json_dumps_serializes_python_date_values() -> None:
    payload = {"effective_on": date(2026, 2, 25)}
    dumped = _json_dumps(payload)
    assert "\"effective_on\": \"2026-02-25\"" in dumped
