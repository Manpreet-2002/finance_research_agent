"""Guardrail helper tests for LangGraph orchestrator."""

from __future__ import annotations

import json

from backend.app.orchestrator.langgraph_finance_agent import (
    LangGraphFinanceAgent,
    _enforce_sheet_tool_scope,
    _to_float_cell,
    _validate_canonical_artifact_metadata,
)


def test_enforce_sheet_scope_injects_missing_spreadsheet_id() -> None:
    args, note = _enforce_sheet_tool_scope(
        tool_name="sheets_write_named_ranges",
        args={"values": {"inp_ticker": "AAPL"}},
        expected_spreadsheet_id="sheet_123",
    )

    assert args["spreadsheet_id"] == "sheet_123"
    assert "injected" in note


def test_enforce_sheet_scope_overrides_mismatched_spreadsheet_id() -> None:
    args, note = _enforce_sheet_tool_scope(
        tool_name="sheets_read_named_ranges",
        args={"spreadsheet_id": "wrong_sheet", "names": ["out_value_ps_weighted"]},
        expected_spreadsheet_id="sheet_123",
    )

    assert args["spreadsheet_id"] == "sheet_123"
    assert "overridden" in note


def test_validate_canonical_artifact_metadata_requires_complete_payload() -> None:
    issues = _validate_canonical_artifact_metadata(
        artifact_path="",
        artifact_sha256="short",
        quality_report={"is_complete": False},
    )

    assert "missing canonical artifact_path" in issues
    assert "missing/invalid canonical artifact_sha256" in issues
    assert "canonical quality_report indicates incomplete required input coverage" in issues


def test_to_float_cell_parses_percent_and_commas() -> None:
    assert _to_float_cell("12.5%") == 0.125
    assert _to_float_cell("1,234.5") == 1234.5
    assert _to_float_cell("bad") is None


def test_to_float_cell_parses_currency_and_multiple_suffix() -> None:
    assert _to_float_cell("$42.10") == 42.10
    assert _to_float_cell("23.6x") == 23.6


class _WeightsSheets:
    def read_named_ranges(self, spreadsheet_id: str, names: list[str], *, value_render_option: str = "UNFORMATTED_VALUE"):
        del spreadsheet_id, names, value_render_option
        return {
            "inp_w_pess": [["0.40"]],
            "inp_w_base": [[""]],
            "inp_w_opt": [["0.30"]],
        }


def test_validate_weights_flags_missing_weight_cells() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    agent.sheets_engine = _WeightsSheets()

    issues = agent._validate_weights("sheet_123")

    assert any("Missing scenario weight: inp_w_base" in issue for issue in issues)


class _WeightsSumSheets:
    def read_named_ranges(self, spreadsheet_id: str, names: list[str], *, value_render_option: str = "UNFORMATTED_VALUE"):
        del spreadsheet_id, names, value_render_option
        return {
            "inp_w_pess": [["0.30"]],
            "inp_w_base": [["0.30"]],
            "inp_w_opt": [["0.30"]],
        }


def test_validate_weights_flags_bad_sum() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    agent.sheets_engine = _WeightsSumSheets()

    issues = agent._validate_weights("sheet_123")

    assert any("must sum to 1.0" in issue for issue in issues)


def test_validate_outputs_requires_per_scenario_outputs() -> None:
    agent = object.__new__(LangGraphFinanceAgent)

    issues = agent._validate_outputs(
        {
            "out_value_ps_weighted": 100.0,
            "out_equity_value_weighted": 1000.0,
            "out_enterprise_value_weighted": 1200.0,
            "out_wacc": 0.09,
            "out_terminal_g": 0.03,
        }
    )

    assert any("out_value_ps_pess" in issue for issue in issues)
    assert any("out_value_ps_base" in issue for issue in issues)
    assert any("out_value_ps_opt" in issue for issue in issues)


class _SensitivityPlaceholderSheets:
    def read_named_ranges(
        self,
        spreadsheet_id: str,
        names: list[str],
        *,
        value_render_option: str = "UNFORMATTED_VALUE",
    ):
        del spreadsheet_id, names, value_render_option
        return {
            "sens_base_value_ps": [["92.0"]],
            "sens_wacc_vector": [["7%"], ["8%"], ["9%"]],
            "sens_terminal_g_vector": [["2%", "2.5%", "3%"]],
            "sens_grid_values": [["(populate via agent scenario sweep)"]],
        }


def test_validate_sensitivity_contract_flags_placeholder_grid_cells() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    agent.sheets_engine = _SensitivityPlaceholderSheets()

    issues = agent._validate_sensitivity_contract("sheet_123")

    assert any("placeholder values remain" in issue for issue in issues)


class _SensitivityWritebackSheets:
    def __init__(self) -> None:
        self._wrote_grid = False
        self.written_values: dict[str, object] = {}

    def read_named_ranges(
        self,
        spreadsheet_id: str,
        names: list[str],
        *,
        value_render_option: str = "UNFORMATTED_VALUE",
    ):
        del spreadsheet_id, value_render_option
        keyset = set(names)
        if keyset == {"sens_wacc_vector", "sens_terminal_g_vector", "sens_grid_values"}:
            return {
                "sens_wacc_vector": [[0.08], [0.09]],
                "sens_terminal_g_vector": [[0.02, 0.025, 0.03]],
                "sens_grid_values": [
                    ["(populate via agent scenario sweep)", "(populate via agent scenario sweep)", "(populate via agent scenario sweep)"],
                    ["(populate via agent scenario sweep)", "(populate via agent scenario sweep)", "(populate via agent scenario sweep)"],
                ],
            }
        if keyset == {"sens_grid_values"} and self._wrote_grid:
            return {
                "sens_grid_values": [
                    [11.3, 10.4, 9.8],
                    [9.7, 8.9, 8.2],
                ]
            }
        return {"sens_grid_values": []}

    def write_named_ranges(self, spreadsheet_id: str, values: dict[str, object]) -> None:
        del spreadsheet_id
        self._wrote_grid = True
        self.written_values = values


def test_enforce_sensitivity_writeback_autofills_placeholder_grid() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    sheets = _SensitivityWritebackSheets()
    agent.sheets_engine = sheets
    agent._persist_tool_call_artifact = lambda **kwargs: None

    issues = agent._enforce_sensitivity_writeback(
        spreadsheet_id="sheet_123",
        run_id="run_123",
        phase_name="validation",
    )

    assert issues == []
    assert "sens_grid_values" in sheets.written_values
    formulas = sheets.written_values["sens_grid_values"]
    assert isinstance(formulas, list)
    assert len(formulas) == 2
    assert len(formulas[0]) == 3
    assert str(formulas[0][0]).startswith("=IFERROR(")
    assert "INDEX(sens_wacc_vector,1,1)" in str(formulas[0][0])


class _MalformedSourcesSheets:
    def read_named_ranges(
        self,
        spreadsheet_id: str,
        names: list[str],
        *,
        value_render_option: str = "UNFORMATTED_VALUE",
    ):
        del spreadsheet_id, names, value_render_option
        return {
            "sources_table": [
                ["SEC", "10-K", "https://example.com", "2026-02-16", "note"],
                ["another", "row"],
                ["x"],
            ]
        }


def test_validate_sources_contract_flags_bad_row_shape_and_fields() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    agent.sheets_engine = _MalformedSourcesSheets()

    issues = agent._validate_sources_contract("sheet_123")

    assert any("malformed source rows" in issue for issue in issues)


class _CompsContractSheetsValid:
    def read_named_ranges(
        self,
        spreadsheet_id: str,
        names: list[str],
        *,
        value_render_option: str = "UNFORMATTED_VALUE",
    ):
        del spreadsheet_id, names, value_render_option
        return {
            "comps_table_full": [
                ["Ticker", "EV/Sales", "EV/EBIT", "P/E", "Notes"],
                ["AAPL", "6.1", "22.4", "30.2", "Target row"],
                ["MSFT", "11.2", "27.0", "34.1", "Peer 1"],
                ["GOOGL", "7.6", "20.8", "24.7", "Peer 2"],
                ["AMZN", "3.1", "18.5", "50.2", "Peer 3"],
            ],
            "comps_peer_count": [[4]],
            "comps_multiple_count": [[3]],
            "comps_method_note": [[
                "Peers selected by software platform exposure and margin structure."
            ]],
            "inp_ticker": [["AAPL"]],
        }


def test_validate_comps_contract_accepts_dynamic_table_with_target_first_row() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    agent.sheets_engine = _CompsContractSheetsValid()

    issues = agent._validate_comps_contract("sheet_123")

    assert issues == []


class _CompsContractSheetsBad:
    def read_named_ranges(
        self,
        spreadsheet_id: str,
        names: list[str],
        *,
        value_render_option: str = "UNFORMATTED_VALUE",
    ):
        del spreadsheet_id, names, value_render_option
        return {
            "comps_table_full": [
                ["Company", "EV/Sales", "EV/EBIT", "Commentary"],
                ["MSFT", "11.2", "27.0", "Peer but wrong target row"],
                ["AAPL", "6.1", "22.4", "Target in wrong row"],
            ],
            "comps_peer_count": [[2]],
            "comps_multiple_count": [[2]],
            "comps_method_note": [["short"]],
            "inp_ticker": [["AAPL"]],
        }


def test_validate_comps_contract_flags_header_and_target_row_violations() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    agent.sheets_engine = _CompsContractSheetsBad()

    issues = agent._validate_comps_contract("sheet_123")

    assert any("first header must be 'Ticker'" in issue for issue in issues)
    assert any("last non-empty header must be 'Notes'" in issue for issue in issues)
    assert any("first data row must be target ticker" in issue for issue in issues)


def test_persist_tool_call_artifact_writes_jsonl_record() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    run_id = "test_tool_artifact_run"
    path = agent._tool_call_artifact_path(run_id)
    if path.exists():
        path.unlink()

    agent._persist_tool_call_artifact(
        run_id=run_id,
        phase="validation",
        tool_name="fetch_research_packet",
        args={"ticker": "AAPL"},
        result={"result": {"ok": True}},
        status="ok",
        mode="native_bind_tools",
        duration_ms=12.5,
    )

    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["run_id"] == run_id
    assert payload["tool"] == "fetch_research_packet"
    assert payload["phase"] == "validation"
    path.unlink()
