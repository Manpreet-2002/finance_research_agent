"""Deterministic phase-based LangGraph orchestrator for V1 valuation runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
import json
import logging
from math import isfinite
from pathlib import Path
import re
from time import perf_counter
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import Field, create_model
from typing_extensions import TypedDict

from ..llm.langchain_gemini import LangChainGeminiClient
from ..orchestrator.state_machine import V1WorkflowStateMachine, WorkflowPhase
from ..schemas.valuation_run import ValuationRunRequest, ValuationRunResult
from ..sheets.engine import SheetsEngine
from ..skills.catalog import SkillSpec
from ..skills.loader import SkillLoader
from ..skills.router import SkillRouter
from ..tools.llm_tools import LlmToolRegistry, ToolSpec
from ..workbook.contract import build_phase_v1_workbook_contract


class FinanceAgentState(TypedDict, total=False):
    """Execution state carried through deterministic LangGraph phases."""

    request: ValuationRunRequest
    run_id: str
    ticker: str
    spreadsheet_id: str
    status: str
    phases_executed: list[str]
    phase_notes: dict[str, str]
    phase_tool_events: dict[str, list[dict[str, Any]]]
    memo_markdown: str
    final_outputs: dict[str, Any]
    notes: list[str]
    citation_items: int
    citation_sources: list[str]
    baseline_inputs_written: bool
    start_ts_utc: str
    canonical_artifact_path: str
    canonical_artifact_sha256: str
    canonical_quality_report: dict[str, Any]
    tool_call_artifact_path: str


class LlmInvokeFailure(RuntimeError):
    """Raised when an LLM invoke call fails and run must hard-stop."""


_CANONICAL_REQUIRED_PREFILL_RANGES: tuple[str, ...] = (
    "inp_rev_ttm",
    "inp_ebit_ttm",
    "inp_tax_ttm",
    "inp_cash",
    "inp_debt",
    "inp_basic_shares",
    "inp_px",
    "inp_rf",
    "inp_tsm_tranche1_count_mm",
    "inp_tsm_tranche1_type",
)

_REQUIRED_SCENARIO_OUTPUT_RANGES: tuple[str, ...] = (
    "out_value_ps_pess",
    "out_value_ps_base",
    "out_value_ps_opt",
    "out_value_ps_weighted",
    "out_equity_value_weighted",
    "out_enterprise_value_weighted",
)

_FINAL_FORMULA_SCAN_RANGES: tuple[str, ...] = (
    "out_value_ps_pess",
    "out_value_ps_base",
    "out_value_ps_opt",
    "out_value_ps_weighted",
    "out_equity_value_weighted",
    "out_enterprise_value_weighted",
    "out_wacc",
    "out_terminal_g",
    "sens_base_value_ps",
    "sens_grid_values",
    "sens_grid_full",
    "checks_statuses",
)

_FORMULA_ERROR_TOKENS: tuple[str, ...] = (
    "#REF!",
    "#N/A",
    "#VALUE!",
    "#DIV/0!",
    "#NAME?",
    "#NUM!",
    "#ERROR!",
)

_COMPS_MIN_PEERS = 3
_COMPS_MIN_MULTIPLES = 3
_COMPS_MIN_NUMERIC_COVERAGE = 0.75
_COMPS_METHOD_NOTE_MIN_CHARS = 80
_COMPS_ROW_NOTE_MIN_CHARS = 120
_COMPS_ROW_NOTE_REQUIRED_SIGNALS: tuple[str, ...] = (
    "business",
    "execution",
    "multiple",
    "valuation",
)
_COMPS_NON_NUMERIC_HEADERS: frozenset[str] = frozenset({"name"})
_SOURCES_MIN_ROWS = 3
_STORY_MIN_TEXT_CHARS = 60
_STORY_MIN_CITATION_ROWS = 3
_STORY_REQUIRED_SCENARIOS: tuple[str, ...] = ("pessimistic", "neutral", "optimistic")
_STORY_MIN_CORE_NARRATIVE_CHARS = 30
_STORY_MIN_OPERATING_DRIVER_CHARS = 20
_STORY_MIN_KPI_CHARS = 8
_STORY_MIN_MEMO_HOOKS = 3
_STORY_MEMO_HOOK_RANGE_TOKEN_RE = re.compile(r"\b(inp_|out_|sens_|comps_)[A-Za-z0-9_]*")
_AUTO_SOURCES_MAX_ROWS = 40
_SENSITIVITY_PLACEHOLDER_TOKENS: tuple[str, ...] = (
    "populate via agent scenario sweep",
)
_AUTO_RESIZE_PRESENTATION_TABS: tuple[str, ...] = (
    "Comps",
    "Sources",
    "Story",
    "Agent Log",
)
_SOURCE_SCHEMA_WIDTH = 11
_CITATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,}$")


@dataclass
class LangGraphFinanceAgent:
    """Deterministic LangGraph orchestrator with per-phase skill/tool routing."""

    llm_client: LangChainGeminiClient
    tool_registry: LlmToolRegistry
    sheets_engine: SheetsEngine
    skill_router: SkillRouter
    state_machine: V1WorkflowStateMachine
    skill_loader: SkillLoader
    max_phase_turns: int = 10
    max_phase_wall_clock_seconds: float = 120.0
    max_llm_invoke_seconds: float = 600.0
    max_validation_repair_passes: int = 2
    _tool_map: dict[str, StructuredTool] = field(default_factory=dict, init=False, repr=False)
    _graph: Any = field(default=None, init=False, repr=False)
    _logger: logging.Logger = field(default_factory=lambda: logging.getLogger("finance_research_agent.orchestrator"), init=False, repr=False)

    _TOOL_DOMAIN_TO_REGISTRY: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "google_sheets": (
                "sheets_write_named_ranges",
                "sheets_read_outputs",
                "sheets_read_named_ranges",
                "sheets_append_named_table_rows",
                "sheets_write_named_table",
            ),
            "sec_edgar_xbrl": ("fetch_sec_filing_fundamentals",),
            "finnhub_fundamentals": (
                "fetch_fundamentals",
                "fetch_market_snapshot",
            ),
            "fred_treasury": ("fetch_rates_snapshot",),
            "earnings_transcripts": ("fetch_transcript_signals",),
            "corporate_actions": ("fetch_corporate_actions",),
            "sector_peer_classification": ("discover_peer_universe",),
            "web_news_search": ("fetch_news_evidence",),
            "source_contradiction_checker": ("check_source_contradictions",),
            "python_math": ("python_execute_math",),
            "llm": (),
        },
        init=False,
        repr=False,
    )

    _PHASE_EXTRA_TOOLS: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "data_collection": (
                "fetch_canonical_dataset",
                "fetch_research_packet",
            ),
            "assumptions": (
                "fetch_canonical_dataset",
                "fetch_research_packet",
            ),
            "model_run": ("sheets_read_outputs",),
            "validation": (
                "sheets_read_outputs",
                "sheets_read_named_ranges",
            ),
            "memo": (
                "sheets_read_outputs",
                "sheets_read_named_ranges",
            ),
            "publish": (
                "sheets_read_outputs",
            ),
        },
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        self._tool_map = self._build_langchain_tools()
        self._graph = self._build_graph()

    def run(self, request: ValuationRunRequest) -> ValuationRunResult:
        self._logger.info("agent_run_start run_id=%s ticker=%s", request.run_id, request.ticker)
        initial_state: FinanceAgentState = {
            "request": request,
            "run_id": request.run_id,
            "ticker": request.ticker.strip().upper(),
            "status": "RUNNING",
            "phases_executed": [],
            "phase_notes": {},
            "phase_tool_events": {},
            "memo_markdown": "",
            "final_outputs": {},
            "notes": [],
            "citation_items": 0,
            "citation_sources": [],
            "baseline_inputs_written": False,
            "start_ts_utc": _utc_now_iso(),
            "canonical_artifact_path": "",
            "canonical_artifact_sha256": "",
            "canonical_quality_report": {},
            "tool_call_artifact_path": "",
        }

        try:
            final_state = self._graph.invoke(
                initial_state,
                config={"configurable": {"thread_id": request.run_id}},
            )
        except LlmInvokeFailure:
            self._logger.exception(
                "agent_run_llm_invoke_failure run_id=%s ticker=%s",
                request.run_id,
                request.ticker,
            )
            raise
        result = self._state_to_result(final_state)
        self._logger.info(
            "agent_run_end run_id=%s status=%s spreadsheet_id=%s",
            result.run_id,
            result.status,
            result.spreadsheet_id,
        )
        return result

    def _build_graph(self) -> Any:
        graph = StateGraph(FinanceAgentState)
        graph.add_node("initialize", self._initialize_node)
        graph.add_edge(START, "initialize")

        previous_node = "initialize"
        for phase in self.state_machine.ordered_phases():
            node_name = f"phase_{phase.value}"
            graph.add_node(node_name, self._make_phase_node(phase))
            graph.add_edge(previous_node, node_name)
            previous_node = node_name

        graph.add_node("finalize", self._finalize_node)
        graph.add_edge(previous_node, "finalize")
        graph.add_edge("finalize", END)
        return graph.compile(checkpointer=MemorySaver())

    def _initialize_node(self, state: FinanceAgentState) -> FinanceAgentState:
        request = state["request"]
        notes = list(state.get("notes") or [])
        ticker = request.ticker.strip().upper()
        canonical_named_ranges: dict[str, Any]
        canonical_artifact_path = ""
        canonical_artifact_sha256 = ""
        canonical_quality_report: dict[str, Any] = {}
        tool_call_artifact_path = str(self._tool_call_artifact_path(request.run_id))

        try:
            tool_started = perf_counter()
            canonical_payload = self.tool_registry.call(
                "fetch_canonical_sheet_inputs",
                {"ticker": ticker},
            )
            self._persist_tool_call_artifact(
                run_id=request.run_id,
                phase="initialize",
                tool_name="fetch_canonical_sheet_inputs",
                args={"ticker": ticker},
                result=canonical_payload,
                status="ok",
                mode="orchestrator_init",
                duration_ms=(perf_counter() - tool_started) * 1000.0,
            )
            canonical_result = (
                canonical_payload.get("result", {})
                if isinstance(canonical_payload, dict)
                else {}
            )
            canonical_named_ranges = (
                canonical_result.get("named_ranges", {})
                if isinstance(canonical_result, dict)
                else {}
            )
            canonical_artifact_path = str(
                canonical_result.get("artifact_path", "")
                if isinstance(canonical_result, dict)
                else ""
            ).strip()
            canonical_artifact_sha256 = str(
                canonical_result.get("artifact_sha256", "")
                if isinstance(canonical_result, dict)
                else ""
            ).strip()
            raw_quality_report = (
                canonical_result.get("quality_report", {})
                if isinstance(canonical_result, dict)
                else {}
            )
            if isinstance(raw_quality_report, dict):
                canonical_quality_report = raw_quality_report
            if not isinstance(canonical_named_ranges, dict):
                raise RuntimeError("Canonical sheet input payload is not a dict.")
            canonical_issues = _validate_canonical_prefill_payload(
                canonical_named_ranges,
                required_names=_CANONICAL_REQUIRED_PREFILL_RANGES,
            )
            canonical_issues.extend(
                _validate_canonical_artifact_metadata(
                    artifact_path=canonical_artifact_path,
                    artifact_sha256=canonical_artifact_sha256,
                    quality_report=canonical_quality_report,
                )
            )
            if canonical_issues:
                raise RuntimeError(
                    "Canonical dataset readiness check failed: "
                    + "; ".join(canonical_issues)
                )
            notes.append(
                "Canonical dataset prepared before sheet copy "
                f"(prefill_ranges={len(canonical_named_ranges)}; "
                f"artifact={canonical_artifact_path}; sha256={canonical_artifact_sha256[:12]}...)."
            )
        except Exception as exc:
            notes.append(f"Canonical dataset preparation failed: {exc}")
            self._logger.exception(
                "initialize_canonical_prep_failed run_id=%s ticker=%s",
                request.run_id,
                ticker,
            )
            self._persist_tool_call_artifact(
                run_id=request.run_id,
                phase="initialize",
                tool_name="fetch_canonical_sheet_inputs",
                args={"ticker": ticker},
                result={"error": str(exc)},
                status="error",
                mode="orchestrator_init",
            )
            return {"status": "FAILED", "notes": notes}

        try:
            spreadsheet_id = self.sheets_engine.copy_template(
                run_id=request.run_id,
                ticker=request.ticker,
            )
            template_named_ranges = self._validate_run_sheet_contract(spreadsheet_id)
            run_start_ts = str(state.get("start_ts_utc") or _utc_now_iso())
            init_values: dict[str, Any] = {
                "log_run_id": request.run_id,
                "log_status": "RUNNING",
                "log_start_ts": run_start_ts,
                "inp_ticker": ticker,
            }
            for key, value in canonical_named_ranges.items():
                key_str = str(key).strip()
                if key_str in template_named_ranges and key_str.startswith("inp_"):
                    init_values[key_str] = value

            if request.overrides:
                for key, value in request.overrides.items():
                    key_str = str(key)
                    if (
                        (key_str.startswith("inp_") or key_str.startswith("log_"))
                        and key_str in template_named_ranges
                    ):
                        init_values[key_str] = value
                    elif key_str.startswith("inp_") or key_str.startswith("log_"):
                        self._logger.warning(
                            "initialize_override_skipped_unknown_range run_id=%s range=%s",
                            request.run_id,
                            key_str,
                        )
            self.sheets_engine.write_named_ranges(spreadsheet_id, init_values)
            self._logger.info(
                "initialize_success run_id=%s spreadsheet_id=%s initial_writes=%s",
                request.run_id,
                spreadsheet_id,
                len(init_values),
            )
        except Exception as exc:
            notes.append(f"Run initialization failed: {exc}")
            self._logger.exception("initialize_failed run_id=%s", request.run_id)
            return {"status": "FAILED", "notes": notes}

        notes.append(
            "Run initialized with canonical prefill on spreadsheet_id="
            f"{spreadsheet_id}"
        )
        return {
            "spreadsheet_id": spreadsheet_id,
            "notes": notes,
            "baseline_inputs_written": True,
            "canonical_artifact_path": canonical_artifact_path,
            "canonical_artifact_sha256": canonical_artifact_sha256,
            "canonical_quality_report": canonical_quality_report,
            "tool_call_artifact_path": tool_call_artifact_path,
        }

    def _make_phase_node(self, phase: WorkflowPhase):
        def _node(state: FinanceAgentState) -> FinanceAgentState:
            if state.get("status") == "FAILED":
                return {}

            skill_specs = self.skill_router.route_for_phase(phase)
            tool_names = self._resolve_phase_tool_names(phase, skill_specs)
            self._logger.info(
                "phase_start run_id=%s phase=%s tools=%s skills=%s",
                state.get("run_id"),
                phase.value,
                ",".join(tool_names),
                ",".join(skill.skill_id for skill in skill_specs),
            )
            system_prompt = self._build_phase_system_prompt(
                phase=phase,
                skill_specs=skill_specs,
                tool_names=tool_names,
                run_id=str(state.get("run_id") or ""),
            )
            user_prompt = self._build_phase_user_prompt(phase=phase, state=state)

            response_text, tool_events = self._run_phase_llm_turns(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tool_names=tool_names,
                expected_spreadsheet_id=str(state.get("spreadsheet_id") or ""),
                run_id=str(state.get("run_id") or ""),
                phase_name=phase.value,
            )
            phase_gate_issues: list[str] = []
            if phase == WorkflowPhase.DATA_QUALITY_CHECKS:
                spreadsheet_id = str(state.get("spreadsheet_id") or "").strip()
                if not spreadsheet_id:
                    phase_gate_issues.append("Missing spreadsheet_id for data quality checks.")
                else:
                    phase_gate_issues.extend(
                        self._validate_data_quality_inputs(spreadsheet_id)
                    )
                if phase_gate_issues:
                    self._logger.warning(
                        "phase_data_quality_gate_failed run_id=%s issues=%s",
                        state.get("run_id"),
                        phase_gate_issues,
                    )
            if phase == WorkflowPhase.VALIDATION:
                spreadsheet_id = str(state.get("spreadsheet_id") or "").strip()
                run_id = str(state.get("run_id") or "")
                validation_repair_count = 0
                while True:
                    phase_gate_issues = self._collect_validation_gate_issues(
                        spreadsheet_id=spreadsheet_id,
                        run_id=run_id,
                        phase_name=phase.value,
                    )
                    if not phase_gate_issues:
                        break

                    self._logger.warning(
                        "phase_validation_gate_failed run_id=%s repair=%s issues=%s",
                        state.get("run_id"),
                        validation_repair_count,
                        phase_gate_issues,
                    )
                    if validation_repair_count >= self.max_validation_repair_passes:
                        break

                    repair_issue_preview = "; ".join(phase_gate_issues[:4])
                    repair_prompt = (
                        f"{user_prompt}\n\n"
                        "Validation gate failed. Repair ALL listed issues before ending this phase.\n"
                        "Rules:\n"
                        "- Use only Google Sheets named-range tools.\n"
                        "- Keep valuation math in-sheet.\n"
                        "- For comps_table_full: header must start 'Ticker', end 'Notes', "
                        "and include >=3 valuation multiples.\n"
                        "- Populate Story required ranges and scenario linkage rows.\n"
                        f"Current issues: {repair_issue_preview}"
                    )
                    repair_response, repair_events = self._run_phase_llm_turns(
                        system_prompt=system_prompt,
                        user_prompt=repair_prompt,
                        tool_names=tool_names,
                        expected_spreadsheet_id=spreadsheet_id,
                        run_id=run_id,
                        phase_name=phase.value,
                    )
                    if repair_response:
                        response_text = "\n".join(
                            filter(
                                None,
                                [
                                    response_text,
                                    f"[validation_repair_{validation_repair_count + 1}] {repair_response}",
                                ],
                            )
                        )
                    if repair_events:
                        tool_events.extend(repair_events)
                    validation_repair_count += 1
            self._logger.info(
                "phase_end run_id=%s phase=%s tool_events=%s",
                state.get("run_id"),
                phase.value,
                len(tool_events),
            )

            phase_notes = dict(state.get("phase_notes") or {})
            phase_notes[phase.value] = response_text

            phase_tool_events = dict(state.get("phase_tool_events") or {})
            phase_tool_events[phase.value] = tool_events

            phases_executed = list(state.get("phases_executed") or [])
            phases_executed.append(phase.value)

            citation_items = int(state.get("citation_items") or 0)
            citation_sources = set(state.get("citation_sources") or [])
            for event in tool_events:
                citation_items += int(event.get("citation_count") or 0)
                for source in event.get("citation_sources") or []:
                    citation_sources.add(str(source))

            updates: FinanceAgentState = {
                "phase_notes": phase_notes,
                "phase_tool_events": phase_tool_events,
                "phases_executed": phases_executed,
                "citation_items": citation_items,
                "citation_sources": sorted(citation_sources),
            }
            if phase_gate_issues:
                notes = list(state.get("notes") or [])
                notes.extend(phase_gate_issues)
                updates["notes"] = notes
                updates["status"] = "FAILED"
            if phase == WorkflowPhase.MEMO:
                updates["memo_markdown"] = response_text
            return updates

        return _node

    def _collect_validation_gate_issues(
        self,
        *,
        spreadsheet_id: str,
        run_id: str,
        phase_name: str,
    ) -> list[str]:
        normalized_id = str(spreadsheet_id or "").strip()
        if not normalized_id:
            return ["Missing spreadsheet_id for validation sensitivity writeback."]
        issues: list[str] = []
        issues.extend(
            self._enforce_sensitivity_writeback(
                spreadsheet_id=normalized_id,
                run_id=run_id,
                phase_name=phase_name,
            )
        )
        issues.extend(self._validate_comps_contract(normalized_id))
        issues.extend(self._validate_story_contract(normalized_id))
        return issues

    def _finalize_node(self, state: FinanceAgentState) -> FinanceAgentState:
        notes = list(state.get("notes") or [])
        spreadsheet_id = state.get("spreadsheet_id")
        if not spreadsheet_id:
            notes.append("Missing spreadsheet_id at finalization.")
            return {"status": "FAILED", "notes": notes}

        outputs: dict[str, Any] = {}
        validation_issues: list[str] = []
        status = "COMPLETED"
        run_end_ts = _utc_now_iso()
        request = state.get("request")

        try:
            auto_citation_issues = self._enforce_sources_story_citation_writeback(
                spreadsheet_id=spreadsheet_id,
                run_id=str(state.get("run_id") or ""),
                artifact_path=str(state.get("tool_call_artifact_path") or ""),
            )
            if auto_citation_issues:
                notes.extend(auto_citation_issues)

            outputs = self.sheets_engine.read_outputs(spreadsheet_id)
            validation_issues.extend(self._validate_outputs(outputs))
            validation_issues.extend(self._validate_weights(spreadsheet_id))
            validation_issues.extend(
                self._validate_formula_integrity(spreadsheet_id)
            )
            validation_issues.extend(
                self._validate_sensitivity_contract(spreadsheet_id)
            )
            validation_issues.extend(self._validate_comps_contract(spreadsheet_id))
            validation_issues.extend(self._validate_sources_contract(spreadsheet_id))
            validation_issues.extend(self._validate_story_contract(spreadsheet_id))
        except Exception as exc:
            status = "FAILED"
            validation_issues.append(f"Output read/validation failed: {exc}")
            self._logger.exception(
                "finalize_output_validation_failed run_id=%s spreadsheet_id=%s",
                state.get("run_id"),
                spreadsheet_id,
            )

        if validation_issues:
            status = "FAILED"
            notes.extend(validation_issues)
            self._logger.warning(
                "finalize_validation_issues run_id=%s issues=%s",
                state.get("run_id"),
                validation_issues,
            )

        try:
            self.sheets_engine.write_named_ranges(
                spreadsheet_id,
                {
                    "log_status": status,
                    "log_end_ts": run_end_ts,
                },
            )
        except Exception as exc:
            status = "FAILED"
            notes.append(f"Failed to write final log status: {exc}")
            self._logger.exception(
                "finalize_log_write_failed run_id=%s spreadsheet_id=%s",
                state.get("run_id"),
                spreadsheet_id,
            )

        resize_issues = self._auto_resize_presentation_tabs(spreadsheet_id)
        if resize_issues:
            notes.extend(resize_issues)

        company_name = ""
        try:
            company_ranges = self.sheets_engine.read_named_ranges(
                spreadsheet_id,
                ["inp_name"],
                value_render_option="FORMATTED_VALUE",
            )
            company_name = _first_sheet_cell(company_ranges)
        except Exception:
            self._logger.exception(
                "finalize_company_read_failed run_id=%s spreadsheet_id=%s",
                state.get("run_id"),
                spreadsheet_id,
            )

        try:
            template_name = (
                request.template_filename
                if isinstance(request, ValuationRunRequest)
                else ""
            )
            summary_row = [
                state.get("run_id", ""),
                state.get("start_ts_utc", ""),
                run_end_ts,
                state.get("ticker", ""),
                company_name,
                template_name,
                "us_stocks_valuation_agent_excelgraph_v1",
                self.llm_client.model,
                status,
                outputs.get("out_value_ps_weighted"),
                outputs.get("out_wacc"),
                outputs.get("out_terminal_g"),
                "",
                "",
                spreadsheet_id,
            ]
            self.sheets_engine.append_logbook_run(
                summary_row
            )
            self._logger.info(
                "finalize_logbook_append_ok run_id=%s row_len=%s",
                state.get("run_id"),
                len(summary_row),
            )
        except Exception as exc:
            notes.append(f"Logbook append failed: {exc}")
            self._logger.exception(
                "finalize_logbook_append_failed run_id=%s spreadsheet_id=%s",
                state.get("run_id"),
                spreadsheet_id,
            )

        self._logger.info(
            "finalize_complete run_id=%s status=%s weighted_value=%s",
            state.get("run_id"),
            status,
            outputs.get("out_value_ps_weighted"),
        )
        return {
            "status": status,
            "final_outputs": outputs,
            "notes": notes,
        }

    def _auto_resize_presentation_tabs(self, spreadsheet_id: str) -> list[str]:
        auto_resize = getattr(self.sheets_engine, "auto_resize_tabs", None)
        if not callable(auto_resize):
            self._logger.info(
                "auto_resize_skipped spreadsheet_id=%s reason=unsupported_engine",
                spreadsheet_id,
            )
            return []
        try:
            result = auto_resize(
                spreadsheet_id,
                list(_AUTO_RESIZE_PRESENTATION_TABS),
            )
            self._logger.info(
                "auto_resize_complete spreadsheet_id=%s tabs=%s result=%s",
                spreadsheet_id,
                ",".join(_AUTO_RESIZE_PRESENTATION_TABS),
                result,
            )
            return []
        except Exception as exc:
            self._logger.exception(
                "auto_resize_failed spreadsheet_id=%s tabs=%s",
                spreadsheet_id,
                ",".join(_AUTO_RESIZE_PRESENTATION_TABS),
            )
            return [f"Post-run sheet auto-resize failed: {exc}"]

    def _state_to_result(self, state: FinanceAgentState) -> ValuationRunResult:
        outputs = state.get("final_outputs") or {}

        weighted_value = _to_float(outputs.get("out_value_ps_weighted"))
        equity_value = _to_float(outputs.get("out_equity_value_weighted"))
        enterprise_value = _to_float(outputs.get("out_enterprise_value_weighted"))

        return ValuationRunResult(
            run_id=str(state.get("run_id") or ""),
            status=str(state.get("status") or "FAILED"),
            value_per_share=weighted_value,
            equity_value=equity_value,
            enterprise_value=enterprise_value,
            notes="\n".join(state.get("notes") or []),
            spreadsheet_id=state.get("spreadsheet_id"),
            memo_markdown=str(state.get("memo_markdown") or ""),
            citations_summary={
                "citation_items": int(state.get("citation_items") or 0),
                "citation_sources": len(set(state.get("citation_sources") or [])),
            },
            pending_questions=(),
            phases_executed=tuple(state.get("phases_executed") or []),
            skills_planned=self._skills_plan_map(),
        )

    def _skills_plan_map(self) -> dict[str, tuple[str, ...]]:
        plan: dict[str, tuple[str, ...]] = {}
        for phase in self.state_machine.ordered_phases():
            plan[phase.value] = tuple(
                skill.skill_id for skill in self.skill_router.route_for_phase(phase)
            )
        return plan

    def _tool_call_artifact_path(self, run_id: str) -> Path:
        safe = "".join(
            char if char.isalnum() or char in {"-", "_", "."} else "_"
            for char in str(run_id or "").strip()
        ).strip("._")
        if not safe:
            safe = "run"
        return Path("artifacts") / "canonical_datasets" / f"{safe}_tool_calls.jsonl"

    def _persist_tool_call_artifact(
        self,
        *,
        run_id: str,
        phase: str,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
        status: str,
        mode: str,
        duration_ms: float | None = None,
        guardrail: str = "",
    ) -> None:
        path = self._tool_call_artifact_path(run_id)
        record = {
            "timestamp_utc": _utc_now_iso(),
            "run_id": run_id,
            "phase": phase,
            "tool": tool_name,
            "mode": mode,
            "status": status,
            "guardrail": guardrail,
            "duration_ms": duration_ms,
            "args": _to_jsonable(args),
            "result": _to_jsonable(result),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=_json_default))
                handle.write("\n")
        except Exception:
            self._logger.exception(
                "tool_call_artifact_write_failed run_id=%s phase=%s tool=%s path=%s",
                run_id,
                phase,
                tool_name,
                path,
            )

    def _build_langchain_tools(self) -> dict[str, StructuredTool]:
        tools: dict[str, StructuredTool] = {}
        for spec in self.tool_registry.specs():
            args_model = _build_args_model(spec)

            def _tool_callable_factory(tool_name: str):
                def _tool_callable(**kwargs: Any) -> str:
                    result = self.tool_registry.call(tool_name, kwargs)
                    return json.dumps(result, default=_json_default)

                return _tool_callable

            tools[spec.name] = StructuredTool.from_function(
                name=spec.name,
                description=spec.description,
                func=_tool_callable_factory(spec.name),
                args_schema=args_model,
                infer_schema=False,
            )
        return tools

    def _run_phase_llm_turns(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tool_names: tuple[str, ...],
        expected_spreadsheet_id: str,
        run_id: str,
        phase_name: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        if not tool_names:
            chat_model = self.llm_client.get_chat_model()
            try:
                response = self._invoke_with_timeout(
                    chat_model,
                    [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_prompt),
                    ],
                    timeout_seconds=self.max_llm_invoke_seconds,
                    context="phase_no_tools",
                )
            except TimeoutError as exc:
                self._logger.exception(
                    "phase_llm_timeout_hard_fail run_id=%s phase=%s context=no_tools",
                    run_id,
                    phase_name,
                )
                raise LlmInvokeFailure(
                    f"LLM invoke timeout in phase '{phase_name}' (no_tools): {exc}"
                ) from exc
            except Exception as exc:
                self._logger.exception(
                    "phase_llm_error_hard_fail run_id=%s phase=%s context=no_tools",
                    run_id,
                    phase_name,
                )
                raise LlmInvokeFailure(
                    f"LLM invoke error in phase '{phase_name}' (no_tools): {exc}"
                ) from exc
            return _message_content_to_text(response.content), []

        messages: list[Any] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        tool_events: list[dict[str, Any]] = []
        phase_started = perf_counter()

        tools = [self._tool_map[name] for name in tool_names if name in self._tool_map]
        chat_model = self.llm_client.get_chat_model()
        model = chat_model.bind_tools(tools)

        final_response = ""
        try:
            for turn_idx in range(self.max_phase_turns):
                if (perf_counter() - phase_started) > self.max_phase_wall_clock_seconds:
                    tool_events.append(
                        {
                            "tool": "__phase_guardrail__",
                            "args": {},
                            "citation_count": 0,
                            "citation_sources": [],
                            "guardrail": (
                                "phase_wall_clock_timeout_exceeded "
                                f"({self.max_phase_wall_clock_seconds}s)"
                            ),
                        }
                    )
                    if not final_response:
                        final_response = (
                            "Phase stopped due to wall-clock timeout guardrail; "
                            "continue with conservative defaults and log degraded status."
                        )
                    break
                try:
                    ai_message = self._invoke_with_timeout(
                        model,
                        messages,
                        timeout_seconds=self.max_llm_invoke_seconds,
                        context="phase_tool_loop",
                    )
                except TimeoutError as exc:
                    self._logger.exception(
                        "phase_llm_timeout_hard_fail run_id=%s phase=%s context=phase_tool_loop",
                        run_id,
                        phase_name,
                    )
                    raise LlmInvokeFailure(
                        f"LLM invoke timeout in phase '{phase_name}' (tool_loop): {exc}"
                    ) from exc
                except Exception as exc:
                    self._logger.exception(
                        "phase_llm_error_hard_fail run_id=%s phase=%s context=phase_tool_loop",
                        run_id,
                        phase_name,
                    )
                    raise LlmInvokeFailure(
                        f"LLM invoke error in phase '{phase_name}' (tool_loop): {exc}"
                    ) from exc
                # Keep the original AIMessage object in history so provider-specific
                # tool metadata (including Gemini thought signatures) is preserved.
                messages.append(ai_message)

                final_response = _message_content_to_text(ai_message.content)
                tool_calls = list(getattr(ai_message, "tool_calls", []) or [])
                if not tool_calls:
                    validation_contract_issues = self._validation_exit_contract_issues(
                        phase_name=phase_name,
                        spreadsheet_id=expected_spreadsheet_id,
                    )
                    if validation_contract_issues:
                        issue_preview = "; ".join(validation_contract_issues[:3])
                        tool_events.append(
                            {
                                "tool": "__phase_guardrail__",
                                "args": {},
                                "citation_count": 0,
                                "citation_sources": [],
                                "guardrail": (
                                    "validation_contract_incomplete "
                                    f"issues={issue_preview}"
                                ),
                            }
                        )
                        if turn_idx < (self.max_phase_turns - 1):
                            messages.append(
                                HumanMessage(
                                    content=(
                                        "Validation phase cannot complete until validation contracts are satisfied.\n"
                                        "Fix now with Google Sheets named-range tools:\n"
                                        "1. Repair comps_table_full with >=3 valuation multiples and IB-grade notes.\n"
                                        "2. Ensure first data row ticker equals inp_ticker and control ranges are set.\n"
                                        "3. Populate all required Story fields and scenario linkage rows.\n"
                                        f"Current validation issues: {issue_preview}"
                                    )
                                )
                            )
                            final_response = (
                                "Validation continuation required: contract incomplete."
                            )
                            continue
                    break

                for tool_call in tool_calls:
                    tool_name = str(tool_call.get("name") or "")
                    tool_id = str(tool_call.get("id") or f"tc_{len(tool_events)+1}")
                    args = _normalize_tool_args(tool_call.get("args"))
                    args, scope_note = _enforce_sheet_tool_scope(
                        tool_name=tool_name,
                        args=args,
                        expected_spreadsheet_id=expected_spreadsheet_id,
                    )

                    tool = self._tool_map.get(tool_name)
                    call_started = perf_counter()
                    call_status = "ok"
                    artifact_result: Any
                    if tool is None:
                        tool_result_text = json.dumps(
                            {"error": f"Unknown tool call: {tool_name}"}
                        )
                        artifact_result = {"error": f"Unknown tool call: {tool_name}"}
                        call_status = "error"
                        citation_count = 0
                        citation_sources: list[str] = []
                    else:
                        try:
                            raw = tool.invoke(args)
                            tool_result_text = _tool_result_to_text(raw)
                        except Exception as exc:
                            tool_result_text = json.dumps(
                                {
                                    "error": str(exc),
                                    "tool": tool_name,
                                }
                            )
                            call_status = "error"

                        payload = _safe_json_loads(tool_result_text)
                        artifact_result = _safe_json_loads_any(tool_result_text)
                        if artifact_result in (None, {}):
                            artifact_result = {"raw_result_text": tool_result_text}
                        citation_count, citation_sources = _extract_citations(payload)
                    if tool is None:
                        artifact_result = {"raw_result_text": tool_result_text}
                    self._persist_tool_call_artifact(
                        run_id=run_id,
                        phase=phase_name,
                        tool_name=tool_name or "__unknown__",
                        args=args,
                        result=artifact_result,
                        status=call_status,
                        mode="native_bind_tools",
                        duration_ms=(perf_counter() - call_started) * 1000.0,
                        guardrail=scope_note,
                    )

                    tool_events.append(
                        {
                            "tool": tool_name,
                            "args": args,
                            "citation_count": citation_count,
                            "citation_sources": citation_sources,
                            "guardrail": scope_note,
                        }
                    )

                    messages.append(
                        ToolMessage(
                            content=_truncate_text(tool_result_text, limit=10_000),
                            tool_call_id=tool_id,
                            name=tool_name,
                        )
                    )
            return final_response, tool_events
        except LlmInvokeFailure:
            raise
        except Exception as exc:
            self._logger.exception(
                "phase_llm_unhandled_hard_fail run_id=%s phase=%s",
                run_id,
                phase_name,
            )
            raise LlmInvokeFailure(
                f"Unexpected LLM phase failure in '{phase_name}': {exc}"
            ) from exc

    def _validation_exit_contract_issues(
        self,
        *,
        phase_name: str,
        spreadsheet_id: str,
    ) -> list[str]:
        if phase_name != WorkflowPhase.VALIDATION.value:
            return []
        normalized_id = str(spreadsheet_id or "").strip()
        if not normalized_id:
            return ["Missing spreadsheet_id for validation contract checks."]
        try:
            issues: list[str] = []
            issues.extend(self._validate_comps_contract(normalized_id))
            issues.extend(self._validate_story_contract(normalized_id))
            return issues
        except Exception as exc:
            return [f"Validation contract checks failed: {exc}"]

    def _invoke_with_timeout(
        self,
        model: Any,
        messages: list[Any],
        *,
        timeout_seconds: float,
        context: str,
    ) -> Any:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(model.invoke, messages)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(
                f"model.invoke timeout after {timeout_seconds:.1f}s ({context})"
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _run_phase_planner_executor(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tool_names: tuple[str, ...],
        failure_message: str,
        expected_spreadsheet_id: str,
        run_id: str,
        phase_name: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Fallback planner-executor when Gemini function-calling is unavailable."""
        self._logger.warning(
            "planner_executor_fallback reason=%s tools=%s",
            failure_message,
            ",".join(tool_names),
        )
        chat_model = self.llm_client.get_chat_model()
        allowed_specs = [self.tool_registry.spec(name) for name in tool_names]
        catalog_lines = []
        for spec in allowed_specs:
            catalog_lines.append(
                f"- {spec.name}: schema={json.dumps(spec.input_schema, default=_json_default)}"
            )
        planner_prompt = (
            "Native function-calling is unavailable in this run. "
            "Plan tool usage in strict JSON.\n"
            "Return JSON object with keys:\n"
            "1. actions: list of {tool, args}\n"
            "2. objective: short sentence\n"
            "Rules:\n"
            "- Use only available tools.\n"
            "- Keep action count <= 12.\n"
            "- Args must satisfy tool schema.\n\n"
            "Available tools:\n"
            f"{chr(10).join(catalog_lines)}\n\n"
            f"Failure context: {failure_message}\n"
        )

        try:
            plan_response = self._invoke_with_timeout(
                chat_model,
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=f"{user_prompt}\n\n{planner_prompt}"),
                ],
                timeout_seconds=self.max_llm_invoke_seconds,
                context="planner_executor_plan",
            )
        except TimeoutError as exc:
            raise LlmInvokeFailure(
                f"LLM invoke timeout in phase '{phase_name}' (planner_plan): {exc}"
            ) from exc
        except Exception as exc:
            raise LlmInvokeFailure(
                f"LLM invoke error in phase '{phase_name}' (planner_plan): {exc}"
            ) from exc
        plan_payload = _extract_json_payload(_message_content_to_text(plan_response.content))
        actions = plan_payload.get("actions")
        if not isinstance(actions, list):
            actions = []
        self._logger.info("planner_executor_actions_planned count=%s", len(actions))

        tool_events: list[dict[str, Any]] = []
        result_lines: list[str] = []
        for idx, action in enumerate(actions[:12], start=1):
            if not isinstance(action, dict):
                continue
            tool_name = str(action.get("tool") or "").strip()
            args = action.get("args")
            if not isinstance(args, dict):
                args = {}
            args, scope_note = _enforce_sheet_tool_scope(
                tool_name=tool_name,
                args=args,
                expected_spreadsheet_id=expected_spreadsheet_id,
            )

            if tool_name not in tool_names:
                self._persist_tool_call_artifact(
                    run_id=run_id,
                    phase=phase_name,
                    tool_name=tool_name or "__unknown__",
                    args=args,
                    result={"error": "Tool not allowed in this phase."},
                    status="rejected",
                    mode="planner_executor",
                    guardrail=scope_note,
                )
                tool_events.append(
                    {
                        "tool": tool_name,
                        "args": args,
                        "citation_count": 0,
                        "citation_sources": [],
                        "error": "Tool not allowed in this phase.",
                    }
                )
                continue

            call_started = perf_counter()
            call_status = "ok"
            try:
                raw_result = self.tool_registry.call(tool_name, args)
            except Exception as exc:
                raw_result = {"error": str(exc)}
                call_status = "error"
                self._logger.exception(
                    "planner_executor_tool_failed tool=%s args=%s",
                    tool_name,
                    args,
                )
            else:
                self._logger.info(
                    "planner_executor_tool_ok tool=%s args_keys=%s",
                    tool_name,
                    ",".join(sorted(args.keys())),
                )
            self._persist_tool_call_artifact(
                run_id=run_id,
                phase=phase_name,
                tool_name=tool_name,
                args=args,
                result=raw_result,
                status=call_status,
                mode="planner_executor",
                duration_ms=(perf_counter() - call_started) * 1000.0,
                guardrail=scope_note,
            )

            citation_count, citation_sources = _extract_citations(
                raw_result if isinstance(raw_result, dict) else {}
            )
            tool_events.append(
                {
                    "tool": tool_name,
                    "args": args,
                    "citation_count": citation_count,
                    "citation_sources": citation_sources,
                    "guardrail": scope_note,
                }
            )
            result_lines.append(
                f"{idx}. {tool_name}: {json.dumps(raw_result, default=_json_default)[:4000]}"
            )

        try:
            summary_response = self._invoke_with_timeout(
                chat_model,
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(
                        content=(
                            f"{user_prompt}\n\n"
                            "Tool execution results:\n"
                            f"{chr(10).join(result_lines) if result_lines else 'No tool actions executed.'}\n\n"
                            "Provide concise markdown summary: decisions, key evidence, assumptions/defaults, and handoff."
                        )
                    ),
                ],
                timeout_seconds=self.max_llm_invoke_seconds,
                context="planner_executor_summary",
            )
        except TimeoutError as exc:
            raise LlmInvokeFailure(
                f"LLM invoke timeout in phase '{phase_name}' (planner_summary): {exc}"
            ) from exc
        except Exception as exc:
            raise LlmInvokeFailure(
                f"LLM invoke error in phase '{phase_name}' (planner_summary): {exc}"
            ) from exc
        return _message_content_to_text(summary_response.content), tool_events

    def _resolve_phase_tool_names(
        self,
        phase: WorkflowPhase,
        skill_specs: tuple[SkillSpec, ...],
    ) -> tuple[str, ...]:
        selected: set[str] = set()
        for skill in skill_specs:
            for domain in skill.required_tools:
                for tool_name in self._TOOL_DOMAIN_TO_REGISTRY.get(domain, ()):  # noqa: SIM118
                    selected.add(tool_name)

        for tool_name in self._PHASE_EXTRA_TOOLS.get(phase.value, ()):
            selected.add(tool_name)

        ordered = []
        for tool_name in self.tool_registry.names():
            if tool_name in selected:
                ordered.append(tool_name)
        return tuple(ordered)

    def _build_phase_system_prompt(
        self,
        *,
        phase: WorkflowPhase,
        skill_specs: tuple[SkillSpec, ...],
        tool_names: tuple[str, ...],
        run_id: str,
    ) -> str:
        skills_block = []
        for spec in skill_specs:
            skill_markdown = self.skill_loader.load_skill_markdown(spec.skill_path)
            self._logger.info(
                "phase_skill_loaded run_id=%s phase=%s skill_id=%s path=%s chars=%s tools=%s ranges=%s",
                run_id,
                phase.value,
                spec.skill_id,
                spec.skill_path,
                len(skill_markdown),
                ",".join(spec.required_tools),
                ",".join(spec.named_ranges),
            )
            skills_block.append(
                f"### SKILL: {spec.skill_id}\n{skill_markdown}"
            )

        shared_quality = self.skill_loader.load_shared_quality_bundle()
        phase_refs = self.skill_loader.load_phase_reference_bundle(phase.value)
        self._logger.info(
            "phase_prompt_bundles_loaded run_id=%s phase=%s shared_quality_chars=%s phase_refs_chars=%s",
            run_id,
            phase.value,
            len(shared_quality),
            len(phase_refs),
        )
        allowed_named_ranges_line = ""
        if "sheets_write_named_ranges" in tool_names:
            allowed_named_ranges = self._phase_allowed_named_ranges(skill_specs)
            if allowed_named_ranges:
                allowed_named_ranges_line = (
                    "7. Use sheets_write_named_ranges only with approved template names for this phase: "
                    f"{', '.join(allowed_named_ranges)}.\n"
                )
        allowed_named_tables_line = ""
        if (
            "sheets_write_named_table" in tool_names
            or "sheets_append_named_table_rows" in tool_names
        ):
            allowed_tables = self._phase_allowed_named_tables(skill_specs)
            if allowed_tables:
                allowed_named_tables_line = (
                    "8. Use named-table tools only with approved table names for this phase: "
                    f"{', '.join(allowed_tables)}.\n"
                )

        phase_completion_line = ""
        if phase == WorkflowPhase.MEMO:
            phase_completion_line = (
                "9. Memo phase is incomplete until Story linkage rows are written for all scenarios: "
                "story_core_narrative_rows, story_linked_operating_driver_rows, "
                "story_kpi_to_track_rows, story_memo_hooks, story_grid_citations.\n"
            )
        if phase == WorkflowPhase.VALIDATION:
            phase_completion_line = (
                "9. Validation phase is incomplete until comps contract is satisfied: "
                "write comps_table_full (header + rows), comps_peer_count, "
                "comps_multiple_count, and comps_method_note.\n"
            )

        return (
            "You are the V1 US-stocks finance research agent. "
            "Execute the current deterministic phase with strict discipline.\n\n"
            "Hard constraints:\n"
            "1. All workbook operations must go through Google Sheets API tools.\n"
            "2. Never modify local template files in repository.\n"
            "3. Keep valuation math in Google Sheets formulas only.\n"
            "4. No human-in-the-loop in this run: reason through missing inputs and apply conservative defaults, then log confidence impacts.\n"
            "5. Use named-range tools only. Do not use A1 addresses or row/column coordinates.\n"
            "6. Use source priority and contradiction handling as specified in skills.\n\n"
            f"{allowed_named_ranges_line}"
            f"{allowed_named_tables_line}"
            f"{phase_completion_line}"
            f"Current phase: {phase.value}\n"
            f"Available tools this phase: {', '.join(tool_names) if tool_names else 'none'}\n\n"
            "Return a concise phase summary in markdown, including decisions, tool actions, and handoff to next phase.\n\n"
            "## Phase Skills\n"
            f"{_compact_text('\n\n'.join(skills_block), limit=12_000)}\n\n"
            "## Shared Quality Bundle\n"
            f"{_compact_text(shared_quality, limit=6_000)}\n\n"
            "## Phase References\n"
            f"{_compact_text(phase_refs, limit=6_000)}"
        )

    def _phase_allowed_named_ranges(
        self,
        skill_specs: tuple[SkillSpec, ...],
    ) -> tuple[str, ...]:
        names: set[str] = {
            "inp_ticker",
            "inp_name",
            "log_run_id",
            "log_status",
            "log_start_ts",
            "log_end_ts",
            "log_actions_firstrow",
            "log_assumptions_firstrow",
            "log_story_firstrow",
        }
        for spec in skill_specs:
            for range_name in spec.named_ranges:
                if _is_formula_owned_name(range_name):
                    continue
                names.add(range_name)
        return tuple(sorted(names))

    def _phase_allowed_named_tables(
        self,
        skill_specs: tuple[SkillSpec, ...],
    ) -> tuple[str, ...]:
        known_tables = {
            "comps_table_full",
            "sources_table",
            "log_actions_table",
            "log_assumptions_table",
            "log_story_table",
        }
        names: set[str] = set()
        for spec in skill_specs:
            for range_name in spec.named_ranges:
                if range_name in known_tables:
                    names.add(range_name)
        return tuple(sorted(names))

    def _build_phase_user_prompt(self, *, phase: WorkflowPhase, state: FinanceAgentState) -> str:
        context_payload = {
            "run_id": state.get("run_id"),
            "ticker": state.get("ticker"),
            "spreadsheet_id": state.get("spreadsheet_id"),
            "status": state.get("status"),
            "phases_executed": state.get("phases_executed") or [],
            "phase_notes": state.get("phase_notes") or {},
            "outputs": state.get("final_outputs") or {},
            "notes": state.get("notes") or [],
            "overrides": getattr(state.get("request"), "overrides", {}),
        }
        context_json = json.dumps(context_payload, indent=2, default=_json_default)

        return (
            f"Execute phase '{phase.value}' for ticker {state.get('ticker')}.\n"
            "Prioritize correctness and auditability.\n"
            "Use tools where needed; do not fabricate source-backed facts.\n"
            "When uncertain and no direct evidence exists, choose conservative assumptions and log reduced confidence.\n\n"
            "Context:\n"
            f"{context_json}"
        )

    def _validate_run_sheet_contract(self, spreadsheet_id: str) -> set[str]:
        contract = build_phase_v1_workbook_contract()
        inspection = self.sheets_engine.inspect_workbook(spreadsheet_id)
        validation = contract.validate(
            sheet_names=inspection.sheet_names,
            named_ranges=inspection.named_ranges,
        )
        if validation.is_valid:
            return {name for name in inspection.named_ranges if name}

        details = []
        if validation.missing_tabs:
            details.append(f"missing tabs={validation.missing_tabs}")
        if validation.missing_named_ranges:
            details.append(f"missing named ranges={validation.missing_named_ranges}")
        raise RuntimeError("; ".join(details))

    def _validate_outputs(self, outputs: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        for key in _REQUIRED_SCENARIO_OUTPUT_RANGES:
            value = outputs.get(key)
            if value in (None, ""):
                issues.append(f"Missing required output: {key}")
                continue
            if _to_float(value) is None:
                issues.append(f"Non-numeric required output: {key}={value!r}")

        wacc = _to_float(outputs.get("out_wacc"))
        terminal_g = _to_float(outputs.get("out_terminal_g"))
        if wacc is not None and terminal_g is not None and not (wacc > terminal_g):
            issues.append(
                f"Invariant failed: out_wacc ({wacc}) must be greater than out_terminal_g ({terminal_g})."
            )
        return issues

    def _validate_formula_integrity(self, spreadsheet_id: str) -> list[str]:
        issues: list[str] = []
        blocks = self.sheets_engine.read_named_ranges(
            spreadsheet_id,
            list(_FINAL_FORMULA_SCAN_RANGES),
            value_render_option="FORMATTED_VALUE",
        )
        for name, rows in blocks.items():
            for token in _iter_error_tokens(rows):
                issues.append(
                    f"Formula/error token detected in {name}: {token}"
                )
                break

        checks_rows = blocks.get("checks_statuses", [])
        for row in checks_rows:
            for cell in row:
                status = str(cell or "").strip().upper()
                if status and status not in {"PASS"}:
                    issues.append(
                        f"Checks status not PASS: {status}"
                    )
                    return issues
        return issues

    def _validate_sensitivity_contract(self, spreadsheet_id: str) -> list[str]:
        issues: list[str] = []
        blocks = self.sheets_engine.read_named_ranges(
            spreadsheet_id,
            [
                "sens_base_value_ps",
                "sens_wacc_vector",
                "sens_terminal_g_vector",
                "sens_grid_values",
            ],
            value_render_option="UNFORMATTED_VALUE",
        )
        base_value = _to_float_cell(
            _first_sheet_cell(blocks.get("sens_base_value_ps", []))
        )
        if base_value is None:
            issues.append(
                "Sensitivity contract failed: sens_base_value_ps is missing/invalid."
            )

        wacc_points = len(blocks.get("sens_wacc_vector", []))
        gt_row = blocks.get("sens_terminal_g_vector", [])
        gt_points = len(gt_row[0]) if gt_row else 0
        if wacc_points < 3 or gt_points < 3:
            issues.append(
                "Sensitivity contract failed: sensitivity axes are under-filled "
                "(need >=3 WACC points and >=3 terminal-g points)."
            )

        grid_rows = blocks.get("sens_grid_values", [])
        if not grid_rows:
            issues.append("Sensitivity contract failed: sens_grid_values is empty.")
            return issues

        non_numeric = 0
        placeholder_hits = 0
        for row in grid_rows:
            if not isinstance(row, list):
                row = [row]
            for cell in row:
                text = str(cell or "").strip()
                lowered = text.casefold()
                if any(token in lowered for token in _SENSITIVITY_PLACEHOLDER_TOKENS):
                    placeholder_hits += 1
                    continue
                if _to_float_cell(cell) is None:
                    non_numeric += 1

        if placeholder_hits:
            issues.append(
                "Sensitivity contract failed: placeholder values remain in sens_grid_values "
                f"(count={placeholder_hits})."
            )
        if non_numeric:
            issues.append(
                "Sensitivity contract failed: non-numeric sensitivity cells detected "
                f"(count={non_numeric})."
            )
        return issues

    def _enforce_sensitivity_writeback(
        self,
        *,
        spreadsheet_id: str,
        run_id: str,
        phase_name: str,
    ) -> list[str]:
        issues: list[str] = []
        read_args = {
            "spreadsheet_id": spreadsheet_id,
            "names": [
                "sens_wacc_vector",
                "sens_terminal_g_vector",
                "sens_grid_values",
            ],
            "value_render_option": "UNFORMATTED_VALUE",
        }
        read_started = perf_counter()
        blocks = self.sheets_engine.read_named_ranges(**read_args)
        self._persist_tool_call_artifact(
            run_id=run_id,
            phase=phase_name,
            tool_name="sheets_read_named_ranges",
            args=read_args,
            result={"result": blocks},
            status="ok",
            mode="orchestrator_guardrail",
            duration_ms=(perf_counter() - read_started) * 1000.0,
            guardrail="sensitivity_precheck",
        )

        grid_rows = blocks.get("sens_grid_values", [])
        needs_writeback = self._sensitivity_grid_needs_writeback(grid_rows)
        if not needs_writeback:
            return issues

        wacc_rows = blocks.get("sens_wacc_vector", [])
        gt_rows = blocks.get("sens_terminal_g_vector", [])
        row_count = len(wacc_rows)
        col_count = len(gt_rows[0]) if gt_rows and isinstance(gt_rows[0], list) else 0
        if row_count <= 0 or col_count <= 0:
            return [
                "Sensitivity writeback failed: invalid sensitivity axes dimensions "
                f"(wacc_rows={row_count}, gt_cols={col_count})."
            ]

        formulas = self._build_sensitivity_formula_grid(
            rows=row_count,
            cols=col_count,
        )
        write_args = {
            "spreadsheet_id": spreadsheet_id,
            "values": {"sens_grid_values": formulas},
        }
        write_started = perf_counter()
        self.sheets_engine.write_named_ranges(**write_args)
        self._persist_tool_call_artifact(
            run_id=run_id,
            phase=phase_name,
            tool_name="sheets_write_named_ranges",
            args={
                "spreadsheet_id": spreadsheet_id,
                "values": {
                    "sens_grid_values": f"formula_grid_{row_count}x{col_count}"
                },
            },
            result={"ok": True, "written_ranges": 1},
            status="ok",
            mode="orchestrator_guardrail",
            duration_ms=(perf_counter() - write_started) * 1000.0,
            guardrail="sensitivity_formula_writeback",
        )

        post_read_args = {
            "spreadsheet_id": spreadsheet_id,
            "names": ["sens_grid_values"],
            "value_render_option": "UNFORMATTED_VALUE",
        }
        post_read_started = perf_counter()
        post_blocks = self.sheets_engine.read_named_ranges(**post_read_args)
        self._persist_tool_call_artifact(
            run_id=run_id,
            phase=phase_name,
            tool_name="sheets_read_named_ranges",
            args=post_read_args,
            result={"result": post_blocks},
            status="ok",
            mode="orchestrator_guardrail",
            duration_ms=(perf_counter() - post_read_started) * 1000.0,
            guardrail="sensitivity_postcheck",
        )

        post_grid_rows = post_blocks.get("sens_grid_values", [])
        placeholder_hits, non_numeric_hits = self._count_sensitivity_grid_issues(
            post_grid_rows
        )
        if placeholder_hits:
            issues.append(
                "Sensitivity writeback failed: placeholder values remain in sens_grid_values "
                f"(count={placeholder_hits})."
            )
        if non_numeric_hits:
            issues.append(
                "Sensitivity writeback failed: non-numeric cells remain in sens_grid_values "
                f"(count={non_numeric_hits})."
            )
        return issues

    def _sensitivity_grid_needs_writeback(self, grid_rows: list[list[Any]]) -> bool:
        if not grid_rows:
            return True
        placeholder_hits, non_numeric_hits = self._count_sensitivity_grid_issues(grid_rows)
        return placeholder_hits > 0 or non_numeric_hits > 0

    def _count_sensitivity_grid_issues(
        self,
        grid_rows: list[list[Any]],
    ) -> tuple[int, int]:
        placeholder_hits = 0
        non_numeric_hits = 0
        for row in grid_rows:
            if not isinstance(row, list):
                row = [row]
            for cell in row:
                text = str(cell or "").strip()
                lowered = text.casefold()
                if any(token in lowered for token in _SENSITIVITY_PLACEHOLDER_TOKENS):
                    placeholder_hits += 1
                    continue
                if _to_float_cell(cell) is None:
                    non_numeric_hits += 1
        return placeholder_hits, non_numeric_hits

    def _build_sensitivity_formula_grid(self, *, rows: int, cols: int) -> list[list[str]]:
        grid: list[list[str]] = []
        for row_idx in range(1, rows + 1):
            row_formulas: list[str] = []
            for col_idx in range(1, cols + 1):
                row_formulas.append(
                    "="
                    "IFERROR("
                    "sens_base_value_ps"
                    "*((out_wacc-out_terminal_g)/(INDEX(sens_wacc_vector,"
                    f"{row_idx}"
                    ",1)-INDEX(sens_terminal_g_vector,1,"
                    f"{col_idx}"
                    "))),"
                    '""'
                    ")"
                )
            grid.append(row_formulas)
        return grid

    def _validate_weights(self, spreadsheet_id: str) -> list[str]:
        issues: list[str] = []
        weight_names = ("inp_w_pess", "inp_w_base", "inp_w_opt")
        weights = self.sheets_engine.read_named_ranges(
            spreadsheet_id,
            list(weight_names),
        )
        values: list[float] = []
        for name in weight_names:
            raw = _first_sheet_cell(weights.get(name, []))
            if raw in ("", None):
                issues.append(f"Missing scenario weight: {name}")
                continue
            weight = _to_float(raw)
            if weight is None:
                issues.append(f"Invalid scenario weight: {name}={raw!r}")
                continue
            values.append(weight)

        if len(values) == len(weight_names):
            normalized = [
                value / 100.0 if abs(value) > 1.0 else value
                for value in values
            ]
            total = sum(normalized)
            if abs(total - 1.0) > 0.02:
                issues.append(
                    "Scenario weights must sum to 1.0 (or 100%). "
                    f"Observed normalized sum={total:.4f}."
                )
        return issues

    def _validate_data_quality_inputs(self, spreadsheet_id: str) -> list[str]:
        issues: list[str] = []
        ranges = self.sheets_engine.read_named_ranges(
            spreadsheet_id,
            [
                "inp_rev_ttm",
                "inp_ebit_ttm",
                "inp_tax_ttm",
                "inp_px",
                "inp_rf",
                "inp_erp",
                "inp_beta",
                "inp_basic_shares",
            ],
            value_render_option="UNFORMATTED_VALUE",
        )
        required_numeric = (
            "inp_rev_ttm",
            "inp_ebit_ttm",
            "inp_tax_ttm",
            "inp_px",
            "inp_rf",
            "inp_erp",
            "inp_beta",
            "inp_basic_shares",
        )
        for name in required_numeric:
            raw = _first_sheet_cell(ranges.get(name, []))
            value = _to_float_cell(raw)
            if value is None:
                issues.append(f"Data quality check failed: missing/invalid numeric input {name}.")

        revenue = _to_float_cell(_first_sheet_cell(ranges.get("inp_rev_ttm", [])))
        ebit = _to_float_cell(_first_sheet_cell(ranges.get("inp_ebit_ttm", [])))
        tax = _to_float_cell(_first_sheet_cell(ranges.get("inp_tax_ttm", [])))
        price = _to_float_cell(_first_sheet_cell(ranges.get("inp_px", [])))
        rf = _to_float_cell(_first_sheet_cell(ranges.get("inp_rf", [])))
        erp = _to_float_cell(_first_sheet_cell(ranges.get("inp_erp", [])))
        beta = _to_float_cell(_first_sheet_cell(ranges.get("inp_beta", [])))
        shares = _to_float_cell(_first_sheet_cell(ranges.get("inp_basic_shares", [])))

        if revenue is not None and revenue <= 0:
            issues.append("Data quality check failed: inp_rev_ttm must be > 0.")
        if ebit is not None and abs(ebit) > 100_000_000:
            issues.append("Data quality check failed: inp_ebit_ttm magnitude is implausible.")
        if tax is not None and not (-0.10 <= tax <= 0.60):
            issues.append(f"Data quality check failed: inp_tax_ttm out of expected bounds ({tax}).")
        if price is not None and price <= 0:
            issues.append("Data quality check failed: inp_px must be > 0.")
        if rf is not None and not (0.0 <= rf <= 0.15):
            issues.append(f"Data quality check failed: inp_rf out of expected bounds ({rf}).")
        if erp is not None and not (0.0 <= erp <= 0.20):
            issues.append(f"Data quality check failed: inp_erp out of expected bounds ({erp}).")
        if beta is not None and not (0.0 <= beta <= 5.0):
            issues.append(f"Data quality check failed: inp_beta out of expected bounds ({beta}).")
        if shares is not None and shares <= 0:
            issues.append("Data quality check failed: inp_basic_shares must be > 0.")
        return issues

    def _validate_comps_contract(self, spreadsheet_id: str) -> list[str]:
        issues: list[str] = []
        blocks = self.sheets_engine.read_named_ranges(
            spreadsheet_id,
            [
                "comps_table_full",
                "comps_peer_count",
                "comps_multiple_count",
                "comps_method_note",
                "inp_ticker",
            ],
            value_render_option="UNFORMATTED_VALUE",
        )
        peer_count = _to_int_cell(_first_sheet_cell(blocks.get("comps_peer_count", [])))
        multiple_count = _to_int_cell(_first_sheet_cell(blocks.get("comps_multiple_count", [])))
        method_note = _first_sheet_cell(blocks.get("comps_method_note", []))
        target_ticker = str(_first_sheet_cell(blocks.get("inp_ticker", [])) or "").strip().upper()

        table_rows = blocks.get("comps_table_full", [])
        non_empty_rows = [row for row in table_rows if isinstance(row, list) and _row_has_values(row)]
        if len(non_empty_rows) < 2:
            issues.append(
                "Comps contract failed: comps_table_full must include header + at least one data row."
            )
            return issues

        header_row = non_empty_rows[0]
        last_header_idx = _last_non_empty_cell_index(header_row)
        if last_header_idx < 2:
            issues.append(
                "Comps contract failed: header must include Ticker, at least one metric, and Notes."
            )
            return issues

        header_first = str(header_row[0] if header_row else "").strip().casefold()
        header_last = str(header_row[last_header_idx]).strip().casefold()
        if header_first != "ticker":
            issues.append("Comps contract failed: first header must be 'Ticker'.")
        if header_last != "notes":
            issues.append("Comps contract failed: last non-empty header must be 'Notes'.")

        numeric_metric_columns: list[int] = []
        for col_idx in range(1, last_header_idx):
            header_label = str(
                header_row[col_idx] if col_idx < len(header_row) else ""
            ).strip()
            if not header_label:
                continue
            if header_label.casefold() in _COMPS_NON_NUMERIC_HEADERS:
                continue
            numeric_metric_columns.append(col_idx)

        table_multiple_count = len(numeric_metric_columns)
        if table_multiple_count < _COMPS_MIN_MULTIPLES:
            issues.append(
                "Comps contract failed: need >= "
                f"{_COMPS_MIN_MULTIPLES} valuation multiples, found {table_multiple_count}."
            )

        data_rows = non_empty_rows[1:]
        table_peer_count = len(data_rows)
        min_rows_including_target = _COMPS_MIN_PEERS + 1
        if table_peer_count < min_rows_including_target:
            issues.append(
                "Comps contract failed: need >= "
                f"{min_rows_including_target} populated rows including target, found {table_peer_count}."
            )

        if peer_count is None:
            issues.append("Comps contract failed: comps_peer_count is missing/invalid.")
        elif peer_count != table_peer_count:
            issues.append(
                "Comps contract failed: comps_peer_count mismatch "
                f"(expected={table_peer_count}, found={peer_count})."
            )

        if multiple_count is None:
            issues.append("Comps contract failed: comps_multiple_count is missing/invalid.")
        elif multiple_count != table_multiple_count:
            issues.append(
                "Comps contract failed: comps_multiple_count mismatch "
                f"(expected={table_multiple_count}, found={multiple_count})."
            )

        if len(str(method_note or "").strip()) < _COMPS_METHOD_NOTE_MIN_CHARS:
            issues.append(
                "Comps contract failed: comps_method_note is missing/too thin "
                f"(min_chars={_COMPS_METHOD_NOTE_MIN_CHARS})."
            )

        first_row_ticker = str(_cell_at(data_rows, 0, 0) or "").strip().upper()
        if target_ticker:
            if not first_row_ticker:
                issues.append("Comps contract failed: missing target ticker in first data row.")
            elif first_row_ticker != target_ticker:
                issues.append(
                    "Comps contract failed: first data row must be target ticker "
                    f"({target_ticker}), found {first_row_ticker}."
                )

        numeric_cells = 0
        total_cells = max(table_peer_count, 0) * max(table_multiple_count, 0)
        target_missing = 0
        for row_idx, row in enumerate(data_rows):
            ticker = str(_cell_at([row], 0, 0) or "").strip()
            if not ticker:
                issues.append(f"Comps contract failed: missing ticker at data row {row_idx + 1}.")
                break
            notes = str(_cell_at([row], 0, last_header_idx) or "").strip()
            if not notes:
                issues.append(f"Comps contract failed: missing Notes at data row {row_idx + 1}.")
                break
            issues.extend(_validate_comps_note_quality(note=notes, row_idx=row_idx + 1))

            for col_idx in numeric_metric_columns:
                raw = _cell_at([row], 0, col_idx)
                if _to_float_cell(raw) is not None:
                    numeric_cells += 1
                elif row_idx == 0:
                    target_missing += 1

        if total_cells > 0:
            coverage = numeric_cells / total_cells
            if coverage < _COMPS_MIN_NUMERIC_COVERAGE:
                issues.append(
                    "Comps contract failed: numeric coverage too low "
                    f"({coverage:.1%} < {_COMPS_MIN_NUMERIC_COVERAGE:.0%})."
                )
        if target_missing:
            issues.append(
                "Comps contract failed: target row has missing required multiple values "
                f"(missing={target_missing})."
            )
        return issues

    def _validate_sources_contract(self, spreadsheet_id: str) -> list[str]:
        issues: list[str] = []
        blocks = self.sheets_engine.read_named_ranges(
            spreadsheet_id,
            ["sources_table"],
            value_render_option="FORMATTED_VALUE",
        )
        rows = blocks.get("sources_table", [])
        non_empty_rows = [row for row in rows if _row_has_values(row)]
        if len(non_empty_rows) < _SOURCES_MIN_ROWS:
            issues.append(
                "Sources contract failed: not enough source rows "
                f"(required>={_SOURCES_MIN_ROWS}, found={len(non_empty_rows)})."
            )
            return issues

        malformed_rows = 0
        unique_sources: set[str] = set()
        for row in non_empty_rows:
            row_values = [_cell_at([row], 0, col) for col in range(_SOURCE_SCHEMA_WIDTH)]
            field_block = str(row_values[0] or "").strip()
            source_type = str(row_values[1] or "").strip()
            dataset_doc = str(row_values[2] or "").strip()
            url = str(row_values[3] or "").strip()
            as_of_date = str(row_values[4] or "").strip()
            notes = str(row_values[5] or "").strip()
            metric = str(row_values[6] or "").strip()
            value = str(row_values[7] or "").strip()
            transform = str(row_values[9] or "").strip()
            citation_id = str(row_values[10] or "").strip()

            if source_type:
                unique_sources.add(source_type.casefold())

            required_values = (
                field_block,
                source_type,
                dataset_doc,
                url,
                as_of_date,
                notes,
                citation_id,
            )
            if any(not item for item in required_values):
                malformed_rows += 1
                continue
            if not (url.startswith("http://") or url.startswith("https://")):
                malformed_rows += 1
                continue
            if not _looks_like_iso_datetime(as_of_date):
                malformed_rows += 1
                continue
            if not (metric or value or transform):
                malformed_rows += 1
                continue
            if not _looks_like_citation_id(citation_id):
                malformed_rows += 1
        if malformed_rows:
            issues.append(
                "Sources contract failed: malformed source rows "
                f"(count={malformed_rows})."
            )
        if len(unique_sources) < 2:
            issues.append(
                "Sources contract failed: source diversity is too low "
                f"(unique_sources={len(unique_sources)})."
            )
        return issues

    def _validate_story_contract(self, spreadsheet_id: str) -> list[str]:
        issues: list[str] = []
        required_blocks = (
            "story_thesis",
            "story_growth",
            "story_profitability",
            "story_reinvestment",
            "story_risk",
            "story_sanity_checks",
        )
        required_grid_columns = (
            "story_core_narrative_rows",
            "story_linked_operating_driver_rows",
            "story_kpi_to_track_rows",
        )
        blocks = self.sheets_engine.read_named_ranges(
            spreadsheet_id,
            list(required_blocks)
            + [
                "story_grid_header",
                "story_grid_rows",
                "story_grid_citations",
                "story_memo_hooks",
            ]
            + list(required_grid_columns),
            value_render_option="FORMATTED_VALUE",
        )
        for name in required_blocks:
            text = _flatten_text(blocks.get(name, []))
            if len(text) < _STORY_MIN_TEXT_CHARS:
                issues.append(
                    f"Story contract failed: {name} is under-filled "
                    f"(chars={len(text)}, required>={_STORY_MIN_TEXT_CHARS})."
                )

        grid_rows = blocks.get("story_grid_rows", [])
        if len(grid_rows) < len(_STORY_REQUIRED_SCENARIOS):
            issues.append(
                "Story contract failed: story_grid_rows must include scenario rows "
                f"(rows={len(grid_rows)}, required={len(_STORY_REQUIRED_SCENARIOS)})."
            )
        for row_idx, scenario in enumerate(_STORY_REQUIRED_SCENARIOS):
            label = str(_cell_at(grid_rows, row_idx, 0) or "").strip().casefold()
            if not label:
                issues.append(
                    "Story contract failed: scenario row label missing "
                    f"(row={row_idx + 1}, expected~={scenario})."
                )
            elif scenario not in label:
                issues.append(
                    "Story contract failed: scenario row label mismatch "
                    f"(row={row_idx + 1}, expected~={scenario}, found={label!r})."
                )

        grid_column_rules = (
            ("story_core_narrative_rows", _STORY_MIN_CORE_NARRATIVE_CHARS),
            ("story_linked_operating_driver_rows", _STORY_MIN_OPERATING_DRIVER_CHARS),
            ("story_kpi_to_track_rows", _STORY_MIN_KPI_CHARS),
        )
        for range_name, min_chars in grid_column_rules:
            range_rows = blocks.get(range_name, [])
            if len(range_rows) < len(_STORY_REQUIRED_SCENARIOS):
                issues.append(
                    "Story contract failed: missing scenario linkage rows for "
                    f"{range_name} (rows={len(range_rows)}, required={len(_STORY_REQUIRED_SCENARIOS)})."
                )
                continue
            for row_idx, scenario in enumerate(_STORY_REQUIRED_SCENARIOS):
                text = str(_cell_at(range_rows, row_idx, 0) or "").strip()
                if len(text) < min_chars:
                    issues.append(
                        "Story contract failed: under-filled scenario linkage field "
                        f"({range_name}, scenario={scenario}, chars={len(text)}, required>={min_chars})."
                    )

        memo_hook_entries = [
            str(cell).strip()
            for cell in _flatten_cells(blocks.get("story_memo_hooks", []))
            if str(cell or "").strip()
        ]
        if len(memo_hook_entries) < _STORY_MIN_MEMO_HOOKS:
            issues.append(
                "Story contract failed: story_memo_hooks is under-filled "
                f"(entries={len(memo_hook_entries)}, required>={_STORY_MIN_MEMO_HOOKS})."
            )
        unlinked_hook_entries = [
            entry
            for entry in memo_hook_entries
            if not _STORY_MEMO_HOOK_RANGE_TOKEN_RE.search(entry)
        ]
        if unlinked_hook_entries:
            issues.append(
                "Story contract failed: story_memo_hooks entries must reference sheet range tokens "
                "(expected inp_/out_/sens_/comps_ tokens)."
            )

        citation_entries = [
            str(cell).strip()
            for cell in _flatten_cells(blocks.get("story_grid_citations", []))
            if str(cell or "").strip()
        ]
        if len(citation_entries) < _STORY_MIN_CITATION_ROWS:
            issues.append(
                "Story contract failed: story_grid_citations is under-filled "
                f"(entries={len(citation_entries)})."
            )
        invalid_citations = [
            item
            for item in citation_entries
            if not (
                "http://" in item
                or "https://" in item
                or "source:" in item.casefold()
                or _looks_like_citation_id(item)
            )
        ]
        if invalid_citations:
            issues.append(
                "Story contract failed: citation entries must include URLs, source tags, or citation IDs."
            )
        return issues

    def _enforce_sources_story_citation_writeback(
        self,
        *,
        spreadsheet_id: str,
        run_id: str,
        artifact_path: str,
    ) -> list[str]:
        issues: list[str] = []
        blocks = self.sheets_engine.read_named_ranges(
            spreadsheet_id,
            ["sources_table", "story_grid_citations"],
            value_render_option="FORMATTED_VALUE",
        )
        sources_rows = [
            row for row in blocks.get("sources_table", []) if isinstance(row, list) and _row_has_values(row)
        ]
        story_entries = [
            str(cell).strip()
            for cell in _flatten_cells(blocks.get("story_grid_citations", []))
            if str(cell or "").strip()
        ]

        if len(sources_rows) >= _SOURCES_MIN_ROWS and len(story_entries) >= _STORY_MIN_CITATION_ROWS:
            return issues

        artifact_file = Path(artifact_path.strip()) if artifact_path.strip() else self._tool_call_artifact_path(run_id)
        citation_rows = _build_sources_rows_from_tool_artifact(
            artifact_path=artifact_file,
            max_rows=_AUTO_SOURCES_MAX_ROWS,
        )
        if len(sources_rows) < _SOURCES_MIN_ROWS:
            if len(citation_rows) >= _SOURCES_MIN_ROWS:
                self.sheets_engine.write_named_table(
                    spreadsheet_id=spreadsheet_id,
                    table_name="sources_table",
                    rows=citation_rows,
                )
                self._persist_tool_call_artifact(
                    run_id=run_id,
                    phase="finalize",
                    tool_name="orchestrator_guardrail",
                    args={"action": "sources_autofill", "rows": len(citation_rows)},
                    result={"ok": True, "rows_written": len(citation_rows)},
                    status="ok",
                    mode="orchestrator_guardrail",
                )
            else:
                issues.append(
                    "Auto-citation writeback failed: insufficient citation rows to populate sources_table."
                )

        refreshed = self.sheets_engine.read_named_ranges(
            spreadsheet_id,
            ["sources_table", "story_grid_citations"],
            value_render_option="FORMATTED_VALUE",
        )
        story_entries = [
            str(cell).strip()
            for cell in _flatten_cells(refreshed.get("story_grid_citations", []))
            if str(cell or "").strip()
        ]
        if len(story_entries) >= _STORY_MIN_CITATION_ROWS:
            return issues

        refreshed_sources_rows = [
            row
            for row in refreshed.get("sources_table", [])
            if isinstance(row, list) and _row_has_values(row)
        ]
        citation_tokens = _collect_story_citation_tokens(refreshed_sources_rows)
        if len(citation_tokens) < _STORY_MIN_CITATION_ROWS:
            issues.append(
                "Auto-citation writeback failed: insufficient source citation tokens for story_grid_citations."
            )
            return issues

        self.sheets_engine.write_named_ranges(
            spreadsheet_id,
            {
                "story_grid_citations": [
                    [citation_tokens[0]],
                    [citation_tokens[1]],
                    [citation_tokens[2]],
                ]
            },
        )
        self._persist_tool_call_artifact(
            run_id=run_id,
            phase="finalize",
            tool_name="orchestrator_guardrail",
            args={"action": "story_citations_autofill", "count": _STORY_MIN_CITATION_ROWS},
            result={"ok": True, "entries_written": _STORY_MIN_CITATION_ROWS},
            status="ok",
            mode="orchestrator_guardrail",
        )
        return issues


def _build_args_model(spec: ToolSpec) -> type:
    schema = spec.input_schema or {}
    properties = schema.get("properties") if isinstance(schema, dict) else {}
    required = set(schema.get("required") or []) if isinstance(schema, dict) else set()

    fields: dict[str, tuple[Any, Any]] = {}
    if isinstance(properties, dict):
        for field_name, field_schema in properties.items():
            annotation = _annotation_for_field_schema(
                field_schema if isinstance(field_schema, dict) else {}
            )
            description = ""
            if isinstance(field_schema, dict):
                description = str(field_schema.get("description") or "")

            if field_name in required:
                fields[field_name] = (
                    annotation,
                    Field(..., description=description),
                )
            else:
                fields[field_name] = (
                    annotation | None,
                    Field(default=None, description=description),
                )

    model_name = f"{_pascal_case(spec.name)}Args"
    return create_model(model_name, **fields)


def _annotation_for_field_schema(field_schema: dict[str, Any]) -> Any:
    type_name = field_schema.get("type")
    if type_name == "string":
        return str
    if type_name == "integer":
        return int
    if type_name == "number":
        return float
    if type_name == "boolean":
        return bool
    if type_name == "array":
        items_schema = field_schema.get("items")
        if isinstance(items_schema, dict):
            item_type = _annotation_for_field_schema(items_schema)
            return list[item_type]
        return list[str]
    if type_name == "object":
        return dict[str, Any]
    return Any


def _pascal_case(value: str) -> str:
    out = []
    for token in value.replace("-", "_").split("_"):
        token = token.strip()
        if token:
            out.append(token.capitalize())
    return "".join(out) or "Tool"


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    chunks.append(str(text))
        return "\n".join(chunks)
    return str(content)


def _normalize_tool_args(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = _safe_json_loads(value)
        if isinstance(loaded, dict):
            return loaded
    return {}


def _enforce_sheet_tool_scope(
    *,
    tool_name: str,
    args: dict[str, Any],
    expected_spreadsheet_id: str,
) -> tuple[dict[str, Any], str]:
    if not tool_name.startswith("sheets_"):
        return args, ""
    if not expected_spreadsheet_id:
        return args, "missing_expected_spreadsheet_id"

    normalized = dict(args)
    provided = str(normalized.get("spreadsheet_id") or "").strip()
    if provided == expected_spreadsheet_id:
        return normalized, ""
    normalized["spreadsheet_id"] = expected_spreadsheet_id
    if provided:
        return (
            normalized,
            f"spreadsheet_id overridden from {provided} to active run sheet.",
        )
    return normalized, "spreadsheet_id injected from active run context."


def _tool_result_to_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, default=_json_default)


def _is_formula_owned_name(name: str) -> bool:
    normalized = name.strip().lower()
    return normalized.startswith("out_") or normalized.startswith("calc_")


def _iter_error_tokens(rows: list[list[Any]]) -> list[str]:
    hits: list[str] = []
    for row in rows:
        if not isinstance(row, list):
            row = [row]
        for cell in row:
            text = str(cell or "").strip().upper()
            if not text:
                continue
            for token in _FORMULA_ERROR_TOKENS:
                if token in text:
                    hits.append(token)
                    break
    return hits


def _safe_json_loads(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _safe_json_loads_any(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _extract_json_payload(text: str) -> dict[str, Any]:
    payload = _safe_json_loads(text)
    if payload:
        return payload

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    snippet = text[start : end + 1]
    return _safe_json_loads(snippet)


def _extract_citations(payload: dict[str, Any]) -> tuple[int, list[str]]:
    if not payload:
        return 0, []

    citation_items: list[dict[str, Any]] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "citations" and isinstance(child, list):
                    for row in child:
                        if isinstance(row, dict):
                            citation_items.append(row)
                else:
                    _walk(child)
            return
        if isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(payload)

    sources = sorted(
        {
            str(row.get("source"))
            for row in citation_items
            if str(row.get("source") or "").strip()
        }
    )
    return len(citation_items), sources


def _build_sources_rows_from_tool_artifact(
    *,
    artifact_path: Path,
    max_rows: int,
) -> list[list[str]]:
    citation_items = _collect_citation_items_from_tool_artifact(artifact_path)
    if not citation_items:
        return []

    rows: list[list[str]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    source_counts: dict[str, int] = {}
    for citation in citation_items:
        source = str(citation.get("source") or "unknown").strip()
        endpoint = str(citation.get("endpoint") or "unknown_endpoint").strip()
        url = str(citation.get("url") or "").strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        dedupe_key = (source.casefold(), endpoint.casefold(), url)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        source_counts[source] = source_counts.get(source, 0) + 1
        idx = source_counts[source]
        as_of = str(citation.get("accessed_at_utc") or "").strip()
        if not _looks_like_iso_datetime(as_of):
            as_of = _utc_now_iso()
        note = str(citation.get("note") or "").strip() or "Auto-curated from tool-call artifacts."
        metric = str(citation.get("metric") or "").strip()
        value = str(citation.get("value") or "").strip()
        unit = str(citation.get("unit") or "").strip()
        transform = str(citation.get("transform") or "").strip() or "tool_call_artifact_capture"
        citation_id = _make_citation_id(source=source, endpoint=endpoint, ordinal=idx)

        rows.append(
            [
                "auto_capture",
                source or "unknown",
                endpoint or "source_record",
                url,
                as_of,
                note,
                metric,
                value,
                unit,
                transform,
                citation_id,
            ]
        )
        if len(rows) >= max_rows:
            break

    return rows


def _collect_citation_items_from_tool_artifact(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        raw = line.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for citation in _extract_citation_items_from_payload(record.get("result")):
            source = str(citation.get("source") or "").strip()
            endpoint = str(citation.get("endpoint") or "").strip()
            url = str(citation.get("url") or "").strip()
            accessed = str(citation.get("accessed_at_utc") or "").strip()
            key = (source, endpoint, url, accessed)
            if key in seen:
                continue
            seen.add(key)
            items.append(citation)
    return items


def _extract_citation_items_from_payload(value: Any) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if key == "citations" and isinstance(child, list):
                    for row in child:
                        if isinstance(row, dict):
                            collected.append(row)
                else:
                    _walk(child)
            return
        if isinstance(node, list):
            for child in node:
                _walk(child)

    _walk(value)
    return collected


def _collect_story_citation_tokens(rows: list[list[Any]]) -> list[str]:
    tokens: list[str] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        citation_id = str(_cell_at([row], 0, 10) or "").strip()
        url = str(_cell_at([row], 0, 3) or "").strip()
        if citation_id and _looks_like_citation_id(citation_id):
            tokens.append(citation_id)
        elif url.startswith("http://") or url.startswith("https://"):
            tokens.append(url)
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def _make_citation_id(*, source: str, endpoint: str, ordinal: int) -> str:
    source_token = "".join(
        char for char in source.upper() if char.isalnum() or char in {"_", "-"}
    )[:20] or "SRC"
    endpoint_token = "".join(
        char for char in endpoint.upper() if char.isalnum() or char in {"_", "-"}
    )[:20] or "EP"
    return f"SRC-{source_token}-{endpoint_token}-{ordinal:03d}"


def _truncate_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}\n...<truncated>"


def _compact_text(value: str, *, limit: int) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}\n...<truncated for token control>"


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        numeric = float(value)
        if not isfinite(numeric):
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _to_float_cell(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        if cleaned.startswith("$"):
            cleaned = cleaned[1:]
        if cleaned.endswith(("x", "X")):
            cleaned = cleaned[:-1].strip()
            if not cleaned:
                return None
        if cleaned.endswith("%"):
            base = _to_float(cleaned[:-1])
            if base is None:
                return None
            return base / 100.0
        return _to_float(cleaned)
    return _to_float(value)


def _to_int_cell(value: Any) -> int | None:
    numeric = _to_float_cell(value)
    if numeric is None:
        return None
    integer = int(round(numeric))
    if abs(numeric - integer) > 1e-6:
        return None
    return integer


def _cell_at(rows: list[list[Any]], row_idx: int, col_idx: int) -> Any:
    if row_idx < 0 or col_idx < 0:
        return ""
    if row_idx >= len(rows):
        return ""
    row = rows[row_idx]
    if not isinstance(row, list):
        return row if col_idx == 0 else ""
    if col_idx >= len(row):
        return ""
    return row[col_idx]


def _row_has_values(row: list[Any]) -> bool:
    return any(str(cell or "").strip() for cell in row)


def _last_non_empty_cell_index(row: list[Any]) -> int:
    last = -1
    for idx, cell in enumerate(row):
        if str(cell or "").strip():
            last = idx
    return last


def _flatten_cells(rows: list[list[Any]]) -> list[Any]:
    flattened: list[Any] = []
    for row in rows:
        if isinstance(row, list):
            flattened.extend(row)
        else:
            flattened.append(row)
    return flattened


def _flatten_text(rows: list[list[Any]]) -> str:
    chunks = [str(cell).strip() for cell in _flatten_cells(rows) if str(cell or "").strip()]
    return " ".join(chunks)


def _validate_comps_note_quality(*, note: str, row_idx: int) -> list[str]:
    issues: list[str] = []
    text = note.strip()
    if len(text) < _COMPS_ROW_NOTE_MIN_CHARS:
        issues.append(
            "Comps contract failed: Notes row "
            f"{row_idx} is too short for IB-grade rationale "
            f"(chars={len(text)}, required>={_COMPS_ROW_NOTE_MIN_CHARS})."
        )
        return issues

    lowered = text.casefold()
    signal_count = sum(
        1 for token in _COMPS_ROW_NOTE_REQUIRED_SIGNALS if token in lowered
    )
    if signal_count < 3:
        issues.append(
            "Comps contract failed: Notes row "
            f"{row_idx} is missing business/execution/valuation rationale depth."
        )
    if text.count(".") < 2 and text.count(";") < 2:
        issues.append(
            "Comps contract failed: Notes row "
            f"{row_idx} must include multi-part analysis."
        )
    return issues


def _looks_like_iso_datetime(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        datetime.fromisoformat(text)
        return True
    except ValueError:
        return False


def _looks_like_citation_id(value: str) -> bool:
    token = value.strip()
    if not token:
        return False
    lowered = token.casefold()
    if lowered.startswith(("src-", "src_", "cid-", "cid_", "citation:", "cite:")):
        return True
    if " " in token:
        return False
    return bool(_CITATION_ID_RE.match(token))


def _validate_canonical_prefill_payload(
    payload: dict[str, Any],
    *,
    required_names: tuple[str, ...],
) -> list[str]:
    issues: list[str] = []
    if not payload:
        return ["named_ranges payload is empty."]
    for name in required_names:
        if name not in payload:
            issues.append(f"missing required canonical field: {name}")
            continue
        if _is_missing_prefill_value(payload.get(name)):
            issues.append(f"canonical field is empty: {name}")
    return issues


def _is_missing_prefill_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _validate_canonical_artifact_metadata(
    *,
    artifact_path: str,
    artifact_sha256: str,
    quality_report: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if not artifact_path:
        issues.append("missing canonical artifact_path")
    if not artifact_sha256 or len(artifact_sha256) < 32:
        issues.append("missing/invalid canonical artifact_sha256")
    is_complete = bool(quality_report.get("is_complete")) if isinstance(quality_report, dict) else False
    if not is_complete:
        issues.append("canonical quality_report indicates incomplete required input coverage")
    return issues


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


def _first_sheet_cell(values: Any) -> str:
    if isinstance(values, dict):
        for rows in values.values():
            if isinstance(rows, list) and rows and rows[0]:
                first = rows[0]
                if isinstance(first, list) and first:
                    return str(first[0])
                return str(first)
        return ""
    if isinstance(values, list):
        if not values:
            return ""
        first = values[0]
        if isinstance(first, list):
            if not first:
                return ""
            return str(first[0])
        return str(first)
    if values in (None, ""):
        return ""
    return str(values)
