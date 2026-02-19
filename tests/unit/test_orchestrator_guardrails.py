"""Guardrail helper tests for LangGraph orchestrator."""

from __future__ import annotations

import json
import logging

import pytest
from langchain_core.messages import AIMessage

from backend.app.orchestrator.langgraph_finance_agent import (
    LlmInvokeFailure,
    LangGraphFinanceAgent,
    _build_sources_rows_from_tool_artifact,
    _collect_story_citation_tokens,
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


class _StoryContractSheetsMissingLinkage:
    def read_named_ranges(
        self,
        spreadsheet_id: str,
        names: list[str],
        *,
        value_render_option: str = "UNFORMATTED_VALUE",
    ):
        del spreadsheet_id, names, value_render_option
        long_text = (
            "Alphabet story block with explicit operating detail, scenario linkage, "
            "and valuation implications across growth, margins, and risk."
        )
        return {
            "story_thesis": [[long_text]],
            "story_growth": [[long_text]],
            "story_profitability": [[long_text]],
            "story_reinvestment": [[long_text]],
            "story_risk": [[long_text]],
            "story_sanity_checks": [[long_text]],
            "story_grid_header": [[
                "Scenario",
                "Core narrative",
                "Linked operating driver",
                "KPI to track",
                "Disconfirming evidence",
                "Citation / source ID",
            ]],
            "story_grid_rows": [["Pessimistic"], ["Neutral"], ["Optimistic"]],
            "story_core_narrative_rows": [[""], [""], [""]],
            "story_linked_operating_driver_rows": [[""], [""], [""]],
            "story_kpi_to_track_rows": [[""], [""], [""]],
            "story_memo_hooks": [],
            "story_grid_citations": [["SRC-001"], ["SRC-002"], ["SRC-003"]],
        }


def test_validate_story_contract_flags_missing_linkage_fields() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    agent.sheets_engine = _StoryContractSheetsMissingLinkage()

    issues = agent._validate_story_contract("sheet_123")

    assert any("story_core_narrative_rows" in issue for issue in issues)
    assert any("story_linked_operating_driver_rows" in issue for issue in issues)
    assert any("story_kpi_to_track_rows" in issue for issue in issues)
    assert any("story_memo_hooks is under-filled" in issue for issue in issues)


class _StoryContractSheetsComplete:
    def read_named_ranges(
        self,
        spreadsheet_id: str,
        names: list[str],
        *,
        value_render_option: str = "UNFORMATTED_VALUE",
    ):
        del spreadsheet_id, names, value_render_option
        long_text = (
            "Alphabet story block with explicit operating detail, scenario linkage, "
            "and valuation implications across growth, margins, and risk."
        )
        return {
            "story_thesis": [[long_text]],
            "story_growth": [[long_text]],
            "story_profitability": [[long_text]],
            "story_reinvestment": [[long_text]],
            "story_risk": [[long_text]],
            "story_sanity_checks": [[long_text]],
            "story_grid_header": [[
                "Scenario",
                "Core narrative",
                "Linked operating driver",
                "KPI to track",
                "Disconfirming evidence",
                "Citation / source ID",
            ]],
            "story_grid_rows": [["Pessimistic"], ["Neutral"], ["Optimistic"]],
            "story_core_narrative_rows": [[
                "AI ad conversion pressure with search share erosion risk but stable demand."
            ], [
                "Balanced search resilience and cloud execution sustain mid-teen earnings power."
            ], [
                "Gemini monetization and cloud margin step-up drive upside operating leverage."
            ]],
            "story_linked_operating_driver_rows": [[
                "Search monetization rate and CPC trend versus AI answer cannibalization."
            ], [
                "Google Cloud revenue growth and segment operating margin trajectory."
            ], [
                "Enterprise AI attach rate and incremental ad load productivity."
            ]],
            "story_kpi_to_track_rows": [[
                "Search revenue growth % and traffic acquisition cost ratio."
            ], [
                "Cloud operating margin % and backlog growth %."
            ], [
                "Gemini MAU monetization yield and capex/revenue %."
            ]],
            "story_memo_hooks": [[
                "Base claim maps to inp_base_g1, inp_base_m5, and out_value_ps_base."
            ], [
                "Downside case maps to inp_pess_wacc and sens_grid_values stress rows."
            ], [
                "Weighted conclusion maps to inp_w_base/inp_w_opt/inp_w_pess and out_value_ps_weighted."
            ]],
            "story_grid_citations": [["SRC-001"], ["SRC-002"], ["SRC-003"]],
        }


def test_validate_story_contract_accepts_complete_linkage_fields() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    agent.sheets_engine = _StoryContractSheetsComplete()

    issues = agent._validate_story_contract("sheet_123")

    assert issues == []


def test_collect_validation_gate_issues_aggregates_contracts() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    agent._enforce_sensitivity_writeback = (  # type: ignore[method-assign]
        lambda *, spreadsheet_id, run_id, phase_name: [  # noqa: ARG005
            f"sensitivity:{spreadsheet_id}:{run_id}:{phase_name}"
        ]
    )
    agent._validate_comps_contract = (  # type: ignore[method-assign]
        lambda spreadsheet_id: [f"comps:{spreadsheet_id}"]
    )
    agent._validate_story_contract = (  # type: ignore[method-assign]
        lambda spreadsheet_id: [f"story:{spreadsheet_id}"]
    )

    issues = agent._collect_validation_gate_issues(
        spreadsheet_id="sheet_123",
        run_id="run_123",
        phase_name="validation",
    )

    assert issues == [
        "sensitivity:sheet_123:run_123:validation",
        "comps:sheet_123",
        "story:sheet_123",
    ]


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


def test_build_sources_rows_from_tool_artifact_extracts_citation_rows(tmp_path) -> None:
    artifact_path = tmp_path / "tool_calls.jsonl"
    artifact_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "result": {
                            "citations": [
                                {
                                    "source": "finnhub",
                                    "endpoint": "stock/metric",
                                    "url": "https://finnhub.io/api/v1/stock/metric",
                                    "accessed_at_utc": "2026-02-18T16:00:00+00:00",
                                    "note": "unit=provider_native",
                                },
                                {
                                    "source": "fred",
                                    "endpoint": "series/observations",
                                    "url": "https://api.stlouisfed.org/fred/series/observations",
                                    "accessed_at_utc": "2026-02-18T16:00:01+00:00",
                                    "note": "series_id=DGS10",
                                },
                            ]
                        }
                    }
                )
            ]
        ),
        encoding="utf-8",
    )

    rows = _build_sources_rows_from_tool_artifact(
        artifact_path=artifact_path,
        max_rows=10,
    )

    assert len(rows) == 2
    assert rows[0][1] == "finnhub"
    assert rows[0][3].startswith("https://")
    assert rows[0][10].startswith("SRC-")
    assert rows[1][1] == "fred"


def test_collect_story_citation_tokens_prefers_ids_then_urls() -> None:
    rows = [
        [
            "auto_capture",
            "finnhub",
            "stock/metric",
            "https://finnhub.io/api/v1/stock/metric",
            "2026-02-18T16:00:00+00:00",
            "note",
            "",
            "",
            "",
            "tool_call_artifact_capture",
            "SRC-FINNHUB-STOCKMETRIC-001",
        ],
        [
            "auto_capture",
            "tavily",
            "search",
            "https://api.tavily.com/search",
            "2026-02-18T16:00:01+00:00",
            "note",
            "",
            "",
            "",
            "tool_call_artifact_capture",
            "",
        ],
    ]

    tokens = _collect_story_citation_tokens(rows)

    assert tokens[0] == "SRC-FINNHUB-STOCKMETRIC-001"
    assert tokens[1] == "https://api.tavily.com/search"


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
                [
                    "AAPL",
                    "6.1",
                    "22.4",
                    "30.2",
                    (
                        "Business model: integrated premium hardware and services ecosystem "
                        "with recurring monetization. Execution: strong product cadence, cost "
                        "discipline, and consistent free-cash-flow conversion across cycles. "
                        "Valuation multiple rationale: premium multiple supported by mix quality "
                        "and durability versus broad mega-cap peers."
                    ),
                ],
                [
                    "MSFT",
                    "11.2",
                    "27.0",
                    "34.1",
                    (
                        "Business model: enterprise software and cloud platform with sticky "
                        "recurring revenue and high switching costs. Execution: durable cloud "
                        "growth, margin resilience, and disciplined reinvestment profile. "
                        "Valuation multiple rationale: premium multiple reflects superior "
                        "profitability and visibility."
                    ),
                ],
                [
                    "GOOGL",
                    "7.6",
                    "20.8",
                    "24.7",
                    (
                        "Business model: advertising network plus scaled cloud operations with "
                        "data and distribution advantages. Execution: better cost controls while "
                        "maintaining innovation velocity in AI and cloud. Valuation multiple "
                        "rationale: modest discount to highest-quality software peers due to ad "
                        "cyclicality despite strong cash generation."
                    ),
                ],
                [
                    "AMZN",
                    "3.1",
                    "18.5",
                    "50.2",
                    (
                        "Business model: retail logistics platform and hyperscale cloud services "
                        "portfolio with high optionality. Execution: continued efficiency gains in "
                        "fulfillment and sustained cloud backlog conversion. Valuation multiple "
                        "rationale: premium to retail peers justified by platform economics and "
                        "higher-growth cloud exposure."
                    ),
                ],
            ],
            "comps_peer_count": [[4]],
            "comps_multiple_count": [[3]],
            "comps_method_note": [[
                "Peer set selected for comparable scale, recurring revenue quality, and margin "
                "structure. Multiples emphasize EV/Sales, EV/EBIT, and P/E to capture both "
                "growth durability and profitability conversion across the cohort."
            ]],
            "inp_ticker": [["AAPL"]],
        }


def test_validate_comps_contract_accepts_dynamic_table_with_target_first_row() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    agent.sheets_engine = _CompsContractSheetsValid()

    issues = agent._validate_comps_contract("sheet_123")

    assert issues == []


class _NoToolsFailingChatModel:
    def invoke(self, messages: list[object]) -> object:
        del messages
        raise RuntimeError("provider unavailable")


class _NoToolsFailingLlmClient:
    def get_chat_model(self):
        return _NoToolsFailingChatModel()


def test_run_phase_llm_turns_hard_fails_when_no_tools_invoke_fails() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    agent.llm_client = _NoToolsFailingLlmClient()
    agent.max_llm_invoke_seconds = 1.0
    agent._logger = logging.getLogger("test.orchestrator.guardrails")

    with pytest.raises(LlmInvokeFailure):
        agent._run_phase_llm_turns(
            system_prompt="system",
            user_prompt="user",
            tool_names=(),
            expected_spreadsheet_id="sheet_123",
            run_id="run_123",
            phase_name="memo",
        )


class _ToolLoopFailingBoundModel:
    def invoke(self, messages: list[object]) -> object:
        del messages
        raise RuntimeError("tool-loop invoke failed")


class _ToolLoopFailingChatModel:
    def bind_tools(self, tools: list[object]) -> object:
        del tools
        return _ToolLoopFailingBoundModel()


class _ToolLoopFailingLlmClient:
    def get_chat_model(self):
        return _ToolLoopFailingChatModel()


def test_run_phase_llm_turns_hard_fails_when_tool_loop_invoke_fails() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    agent.llm_client = _ToolLoopFailingLlmClient()
    agent.max_phase_turns = 1
    agent.max_phase_wall_clock_seconds = 60.0
    agent.max_llm_invoke_seconds = 1.0
    agent._tool_map = {}
    agent._logger = logging.getLogger("test.orchestrator.guardrails")

    with pytest.raises(LlmInvokeFailure):
        agent._run_phase_llm_turns(
            system_prompt="system",
            user_prompt="user",
            tool_names=("sheets_read_outputs",),
            expected_spreadsheet_id="sheet_123",
            run_id="run_123",
            phase_name="assumptions",
        )


class _ValidationCompsRetryBoundModel:
    def __init__(self) -> None:
        self.invocations = 0

    def invoke(self, messages: list[object]) -> object:
        del messages
        self.invocations += 1
        return AIMessage(content=f"validation_attempt_{self.invocations}", tool_calls=[])


class _ValidationCompsRetryChatModel:
    def __init__(self) -> None:
        self.bound = _ValidationCompsRetryBoundModel()

    def bind_tools(self, tools: list[object]) -> object:
        del tools
        return self.bound


class _ValidationCompsRetryLlmClient:
    def __init__(self) -> None:
        self.chat_model = _ValidationCompsRetryChatModel()

    def get_chat_model(self):
        return self.chat_model


def test_run_phase_llm_turns_retries_validation_when_contract_incomplete() -> None:
    agent = object.__new__(LangGraphFinanceAgent)
    agent.llm_client = _ValidationCompsRetryLlmClient()
    agent.max_phase_turns = 3
    agent.max_phase_wall_clock_seconds = 60.0
    agent.max_llm_invoke_seconds = 1.0
    agent._tool_map = {}
    agent._logger = logging.getLogger("test.orchestrator.validation.comps.retry")

    calls = {"count": 0}

    def _mock_validate_comps(spreadsheet_id: str) -> list[str]:
        assert spreadsheet_id == "sheet_123"
        calls["count"] += 1
        if calls["count"] == 1:
            return ["Comps contract failed: comps_table_full must include header + at least one data row."]
        return []

    agent._validate_comps_contract = _mock_validate_comps  # type: ignore[method-assign]
    agent._validate_story_contract = lambda spreadsheet_id: []  # type: ignore[method-assign]

    response, tool_events = agent._run_phase_llm_turns(
        system_prompt="system",
        user_prompt="user",
        tool_names=("sheets_write_named_table",),
        expected_spreadsheet_id="sheet_123",
        run_id="run_123",
        phase_name="validation",
    )

    assert response == "validation_attempt_2"
    assert calls["count"] >= 2
    assert any(
        "validation_contract_incomplete" in str(event.get("guardrail", ""))
        for event in tool_events
    )


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
