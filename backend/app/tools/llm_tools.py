"""Python tool-call registry with strict input schemas for LLM orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from .contracts import DataSourceCitation
from .data_service import DataService
from .fundamentals.client import FundamentalsClient
from .python_math import execute_python_math
from .research_service import ResearchService
from ..sheets.engine import SheetsEngine


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]
LOGGER = logging.getLogger("finance_research_agent.tools.llm")
_DEGRADABLE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "fetch_news_evidence",
        "fetch_transcript_signals",
        "fetch_corporate_actions",
        "discover_peer_universe",
        "fetch_research_packet",
        "check_source_contradictions",
    }
)
_CANONICAL_QUALITY_REQUIRED_RANGES: tuple[str, ...] = (
    "inp_ticker",
    "inp_name",
    "inp_rev_ttm",
    "inp_ebit_ttm",
    "inp_tax_ttm",
    "inp_da_ttm",
    "inp_capex_ttm",
    "inp_dNWC_ttm",
    "inp_rd_ttm",
    "inp_rent_ttm",
    "inp_cash",
    "inp_debt",
    "inp_basic_shares",
    "inp_px",
    "inp_rf",
    "inp_erp",
    "inp_beta",
    "inp_kd",
    "inp_dw",
    "inp_gt",
    "inp_tsm_tranche1_count_mm",
    "inp_tsm_tranche1_type",
)
_CANONICAL_QUALITY_NUMERIC_BOUNDS: dict[str, tuple[float, float]] = {
    "inp_rev_ttm": (0.0, 10_000_000.0),
    "inp_ebit_ttm": (-5_000_000.0, 5_000_000.0),
    "inp_cash": (0.0, 5_000_000.0),
    "inp_debt": (0.0, 5_000_000.0),
    "inp_basic_shares": (0.0, 10_000_000.0),
    "inp_px": (0.01, 20_000.0),
    "inp_rf": (0.0, 0.15),
    "inp_erp": (0.0, 0.20),
    "inp_beta": (0.0, 5.0),
}
_SOURCES_TABLE_SCHEMA_WIDTH = 11
_SOURCES_REQUIRED_COLUMN_INDEXES: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 10)
_SOURCES_TABLE_HEADER_ROW: tuple[str, ...] = (
    "field_block",
    "source_type",
    "dataset_doc",
    "url",
    "as_of_date",
    "notes",
    "metric",
    "value",
    "unit",
    "transform",
    "citation_id",
)
_COMPS_REQUIRED_HEADER_FIRST = "ticker"
_COMPS_REQUIRED_HEADER_LAST = "notes"
_COMPS_ALLOWED_WRITE_TABLE = "comps_table_full"
_COMPS_TABLE_NAMES: frozenset[str] = frozenset({"comps_table", "comps_table_full"})
_COMPS_NON_NUMERIC_HEADERS: frozenset[str] = frozenset({"name"})
_COMPS_DERIVED_CONTROL_RANGES: frozenset[str] = frozenset(
    {"comps_peer_count", "comps_multiple_count"}
)
_SHEETS_RUNTIME_READ_ONLY_RANGES: frozenset[str] = frozenset(
    {"story_grid_header", "log_status", "log_end_ts"}
)
_LOG_TABLE_SCHEMA_WIDTHS: dict[str, int] = {
    "log_actions_table": 9,
    "log_assumptions_table": 10,
    "log_story_table": 9,
}
_LOG_TABLE_REQUIRED_COLUMN_INDEXES: dict[str, tuple[int, ...]] = {
    "log_actions_table": (0, 1, 2),
    "log_assumptions_table": (0, 1, 2),
    "log_story_table": (0, 1, 2),
}
_SHEETS_MONEY_MM_RANGES: frozenset[str] = frozenset(
    {
        "inp_rev_ttm",
        "inp_ebit_ttm",
        "inp_da_ttm",
        "inp_capex_ttm",
        "inp_dNWC_ttm",
        "inp_rd_ttm",
        "inp_rent_ttm",
        "inp_cash",
        "inp_debt",
        "inp_basic_shares",
        "inp_tsm_tranche1_count_mm",
        "comps_target_rev_ttm",
        "comps_target_ebit_ttm",
    }
)
_SHEETS_RATE_DECIMAL_RANGES: frozenset[str] = frozenset(
    {
        "inp_tax_ttm",
        "inp_tax_norm",
        "inp_rf",
        "inp_erp",
        "inp_kd",
        "inp_dw",
        "inp_gt",
        "inp_g1",
        "inp_g2",
        "inp_g3",
        "inp_g4",
        "inp_g5",
        "inp_m5",
        "inp_m10",
        "inp_w_pess",
        "inp_w_base",
        "inp_w_opt",
        "inp_pess_g1",
        "inp_pess_g2",
        "inp_pess_g3",
        "inp_pess_g4",
        "inp_pess_g5",
        "inp_pess_m5",
        "inp_pess_m10",
        "inp_pess_tax",
        "inp_pess_wacc",
        "inp_pess_gt",
        "inp_base_g1",
        "inp_base_g2",
        "inp_base_g3",
        "inp_base_g4",
        "inp_base_g5",
        "inp_base_m5",
        "inp_base_m10",
        "inp_base_tax",
        "inp_base_wacc",
        "inp_base_gt",
        "inp_opt_g1",
        "inp_opt_g2",
        "inp_opt_g3",
        "inp_opt_g4",
        "inp_opt_g5",
        "inp_opt_m5",
        "inp_opt_m10",
        "inp_opt_tax",
        "inp_opt_wacc",
        "inp_opt_gt",
    }
)
_COMPS_ROW_NOTE_MIN_CHARS = 120
_COMPS_ROW_NOTE_REQUIRED_SIGNALS: tuple[str, ...] = (
    "business",
    "execution",
    "multiple",
    "valuation",
)
_SHEETS_READ_RANGE_ALIASES: dict[str, str] = {}
_TABLE_ROWS_SCHEMA: dict[str, Any] = {
    "type": "array",
    "description": (
        "2D table payload: rows -> columns. Each cell must be a scalar string "
        "(numbers/dates/formulas should be passed as strings)."
    ),
    "items": {
        "type": "array",
        "items": {"type": "string"},
    },
}


@dataclass(frozen=True)
class ToolSpec:
    """Declarative schema + handler definition for an LLM-callable tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


class LlmToolRegistry:
    """Runtime registry that validates payloads before tool execution."""

    def __init__(self, specs: list[ToolSpec]) -> None:
        self._specs = {spec.name: spec for spec in specs}

    def names(self) -> tuple[str, ...]:
        return tuple(self._specs.keys())

    def spec(self, name: str) -> ToolSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._specs[name] for name in self.names())

    def call(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        spec = self.spec(name)
        payload_keys = ",".join(sorted(str(key) for key in payload.keys()))
        LOGGER.info("tool_call_start tool=%s payload_keys=%s", name, payload_keys)
        started = perf_counter()
        self._validate_payload(spec, payload)
        try:
            result = spec.handler(payload)
        except Exception:
            LOGGER.exception("tool_call_failed tool=%s payload_keys=%s", name, payload_keys)
            if name in _DEGRADABLE_TOOL_NAMES:
                result = {
                    "result": {
                        "error": "provider_degraded",
                        "tool": name,
                        "detail": "Upstream provider error. Continuing in degraded mode.",
                    }
                }
            else:
                raise
        elapsed_ms = (perf_counter() - started) * 1000.0
        LOGGER.info("tool_call_end tool=%s elapsed_ms=%.2f", name, elapsed_ms)
        return result

    def _validate_payload(self, spec: ToolSpec, payload: dict[str, Any]) -> None:
        schema = spec.input_schema or {}
        if schema.get("type") != "object":
            return
        required_fields = schema.get("required") or []
        if not isinstance(required_fields, list):
            return
        missing = [field for field in required_fields if field not in payload]
        if missing:
            raise ValueError(
                f"Tool '{spec.name}' missing required fields: {', '.join(missing)}"
            )


def build_phase_v1_tool_registry(
    *,
    data_service: DataService,
    research_service: ResearchService,
    sheets_engine: SheetsEngine | None = None,
    sec_fundamentals_client: FundamentalsClient | None = None,
) -> LlmToolRegistry:
    """Build tool-call registry for V1 orchestration and skill execution."""

    specs: list[ToolSpec] = [
        ToolSpec(
            name="fetch_sec_filing_fundamentals",
            description="Fetch filing-grounded fundamentals from SEC EDGAR/XBRL.",
            input_schema={
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            handler=lambda payload: _json_result(
                _call_sec_fundamentals(
                    client=sec_fundamentals_client,
                    ticker=str(payload["ticker"]).strip().upper(),
                )
            ),
        ),
        ToolSpec(
            name="fetch_fundamentals",
            description="Fetch normalized company fundamentals from configured provider.",
            input_schema={
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            handler=lambda payload: _json_result(
                {
                    "fundamentals": data_service.fundamentals_client.fetch_company_fundamentals(
                        str(payload["ticker"]).strip().upper()
                    ),
                    "citations": data_service.fundamentals_client.fetch_citations(
                        str(payload["ticker"]).strip().upper()
                    ),
                }
            ),
        ),
        ToolSpec(
            name="fetch_market_snapshot",
            description="Fetch market price, beta, shares, and market cap snapshot.",
            input_schema={
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            handler=lambda payload: _json_result(
                {
                    "market": data_service.market_client.fetch_market_snapshot(
                        str(payload["ticker"]).strip().upper()
                    ),
                    "citations": data_service.market_client.fetch_citations(
                        str(payload["ticker"]).strip().upper()
                    ),
                }
            ),
        ),
        ToolSpec(
            name="fetch_rates_snapshot",
            description="Fetch rates/macro snapshot for discount-rate assumptions.",
            input_schema={
                "type": "object",
                "properties": {},
            },
            handler=lambda payload: _json_result(
                {
                    "rates": data_service.rates_client.fetch_rates_snapshot(),
                    "citations": data_service.rates_client.fetch_citations(),
                }
            ),
        ),
        ToolSpec(
            name="fetch_news_evidence",
            description="Fetch company news/web evidence from configured news provider.",
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["ticker"],
            },
            handler=lambda payload: _json_result(
                {
                    "news": data_service.news_client.fetch_company_news(
                        str(payload["ticker"]).strip().upper(),
                        limit=_coerce_optional_int(payload.get("limit"), default=10),
                    ),
                    "citations": data_service.news_client.fetch_citations(
                        str(payload["ticker"]).strip().upper()
                    ),
                }
            ),
        ),
        ToolSpec(
            name="fetch_transcript_signals",
            description="Fetch transcript-derived guidance signals.",
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["ticker"],
            },
            handler=lambda payload: _json_result(
                {
                    "transcript_signals": research_service.transcript_client.fetch_transcript_signals(
                        str(payload["ticker"]).strip().upper(),
                        limit=_coerce_optional_int(payload.get("limit"), default=20),
                    ),
                    "citations": research_service.transcript_client.fetch_citations(
                        str(payload["ticker"]).strip().upper()
                    ),
                }
            ),
        ),
        ToolSpec(
            name="fetch_corporate_actions",
            description="Fetch corporate actions (splits/dividends/etc.).",
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["ticker"],
            },
            handler=lambda payload: _json_result(
                {
                    "corporate_actions": research_service.corporate_actions_client.fetch_corporate_actions(
                        str(payload["ticker"]).strip().upper(),
                        limit=_coerce_optional_int(payload.get("limit"), default=50),
                    ),
                    "citations": research_service.corporate_actions_client.fetch_citations(
                        str(payload["ticker"]).strip().upper()
                    ),
                }
            ),
        ),
        ToolSpec(
            name="discover_peer_universe",
            description="Discover peer set candidates for comps and competitive analysis.",
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["ticker"],
            },
            handler=lambda payload: _json_result(
                {
                    "peers": research_service.peer_client.discover_peers(
                        str(payload["ticker"]).strip().upper(),
                        limit=_coerce_optional_int(payload.get("limit"), default=12),
                    ),
                    "citations": research_service.peer_client.fetch_citations(
                        str(payload["ticker"]).strip().upper()
                    ),
                }
            ),
        ),
        ToolSpec(
            name="check_source_contradictions",
            description="Run source contradiction checks on normalized fact collections.",
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "facts": {"type": "object"},
                    "citations": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["ticker", "facts"],
            },
            handler=lambda payload: _json_result(
                {
                    "contradictions": research_service.contradiction_checker.check_contradictions(
                        ticker=str(payload["ticker"]).strip().upper(),
                        facts=_dict_or_empty(payload.get("facts")),
                        citations=_citations_or_empty(payload.get("citations")),
                    )
                }
            ),
        ),
        ToolSpec(
            name="fetch_canonical_dataset",
            description="Fetch fundamentals/market/rates/news and normalized DCF inputs.",
            input_schema={
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            handler=lambda payload: _json_result(
                data_service.build_canonical_dataset(str(payload["ticker"]).strip().upper())
            ),
        ),
        ToolSpec(
            name="fetch_canonical_sheet_inputs",
            description=(
                "Fetch canonical dataset and return template named-range inputs for sheet hydration."
            ),
            input_schema={
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            handler=lambda payload: _json_result(
                _build_canonical_sheet_inputs(
                    data_service=data_service,
                    ticker=str(payload["ticker"]).strip().upper(),
                )
            ),
        ),
        ToolSpec(
            name="fetch_research_packet",
            description="Fetch transcript, corporate actions, peers, news, and contradictions.",
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "facts": {"type": "object"},
                    "news_limit": {"type": "integer"},
                },
                "required": ["ticker"],
            },
            handler=lambda payload: _json_result(
                research_service.build_research_packet(
                    str(payload["ticker"]).strip().upper(),
                    facts=_dict_or_empty(payload.get("facts")),
                    news_limit=_coerce_optional_int(payload.get("news_limit"), default=12),
                )
            ),
        ),
        ToolSpec(
            name="python_execute_math",
            description=(
                "Execute deterministic bounded Python function for intermediate analytics "
                "(for example comps multiple math)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "inputs": {"type": "object"},
                    "function_name": {"type": "string"},
                    "timeout_seconds": {"type": "number"},
                },
                "required": ["code", "inputs"],
            },
            handler=lambda payload: _json_result(
                execute_python_math(
                    code=str(payload["code"]),
                    inputs=_dict_or_empty(payload.get("inputs")),
                    function_name=str(payload.get("function_name") or "compute"),
                    timeout_seconds=_coerce_optional_float(
                        payload.get("timeout_seconds"), default=2.0
                    ),
                )
            ),
        ),
    ]

    if sheets_engine is not None:
        specs.extend(
            [
                ToolSpec(
                    name="sheets_write_named_ranges",
                    description="Write named-range values into a spreadsheet.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "spreadsheet_id": {"type": "string"},
                            "values": {"type": "object"},
                        },
                        "required": ["spreadsheet_id", "values"],
                    },
                    handler=lambda payload: _call_sheets_write(
                        sheets_engine=sheets_engine,
                        spreadsheet_id=str(payload["spreadsheet_id"]),
                        values=_dict_or_empty(payload["values"]),
                    ),
                ),
                ToolSpec(
                    name="sheets_read_named_ranges",
                    description=(
                        "Read named ranges only from a spreadsheet."
                    ),
                    input_schema={
                        "type": "object",
                        "properties": {
                            "spreadsheet_id": {"type": "string"},
                            "names": {"type": "array", "items": {"type": "string"}},
                            "value_render_option": {"type": "string"},
                        },
                        "required": ["spreadsheet_id", "names"],
                    },
                    handler=lambda payload: _json_result(
                        _call_sheets_read_named_ranges(
                            sheets_engine=sheets_engine,
                            spreadsheet_id=str(payload["spreadsheet_id"]),
                            names=_list_of_strings(payload.get("names")),
                            value_render_option=str(
                                payload.get("value_render_option")
                                or "UNFORMATTED_VALUE"
                            ),
                        )
                    ),
                ),
                ToolSpec(
                    name="sheets_read_outputs",
                    description="Read valuation output ranges from a spreadsheet.",
                    input_schema={
                        "type": "object",
                        "properties": {"spreadsheet_id": {"type": "string"}},
                        "required": ["spreadsheet_id"],
                    },
                    handler=lambda payload: _json_result(
                        sheets_engine.read_outputs(str(payload["spreadsheet_id"]))
                    ),
                ),
                ToolSpec(
                    name="sheets_append_named_table_rows",
                    description=(
                        "Append rows into a named table range (first-empty-row policy)."
                    ),
                    input_schema={
                        "type": "object",
                        "properties": {
                            "spreadsheet_id": {"type": "string"},
                            "table_name": {"type": "string"},
                            "rows": _TABLE_ROWS_SCHEMA,
                        },
                        "required": ["spreadsheet_id", "table_name", "rows"],
                    },
                    handler=lambda payload: _call_sheets_append_named_table_rows(
                        sheets_engine=sheets_engine,
                        spreadsheet_id=str(payload["spreadsheet_id"]),
                        table_name=str(payload["table_name"]),
                        rows=_list_of_rows(payload.get("rows")),
                    ),
                ),
                ToolSpec(
                    name="sheets_write_named_table",
                    description=(
                        "Overwrite a named table range from top-left with structured rows."
                    ),
                    input_schema={
                        "type": "object",
                        "properties": {
                            "spreadsheet_id": {"type": "string"},
                            "table_name": {"type": "string"},
                            "rows": _TABLE_ROWS_SCHEMA,
                        },
                        "required": ["spreadsheet_id", "table_name", "rows"],
                    },
                    handler=lambda payload: _call_sheets_write_named_table(
                        sheets_engine=sheets_engine,
                        spreadsheet_id=str(payload["spreadsheet_id"]),
                        table_name=str(payload["table_name"]),
                        rows=_list_of_rows(payload.get("rows")),
                    ),
                ),
            ]
        )

    return LlmToolRegistry(specs)


def _json_result(value: Any) -> dict[str, Any]:
    return {"result": _to_jsonable(value)}


def _call_sheets_write(
    *, sheets_engine: SheetsEngine, spreadsheet_id: str, values: dict[str, Any]
) -> dict[str, Any]:
    normalized_values = _normalize_named_range_values(values)
    _validate_named_range_write_payload(normalized_values)
    (
        writable_values,
        dropped_ranges,
    ) = _drop_derived_control_range_writes(normalized_values)
    if writable_values:
        sheets_engine.write_named_ranges(
            spreadsheet_id=spreadsheet_id,
            values=writable_values,
        )
    if dropped_ranges:
        LOGGER.info(
            "sheets_write_named_ranges_dropped ranges=%s reason=derived_controls_managed_by_comps_table_write",
            ",".join(dropped_ranges),
        )
    return {
        "ok": True,
        "written_ranges": len(writable_values),
        "dropped_ranges": dropped_ranges,
    }


def _call_sheets_read_named_ranges(
    *,
    sheets_engine: SheetsEngine,
    spreadsheet_id: str,
    names: list[str],
    value_render_option: str,
) -> dict[str, list[list[object]]]:
    requested_names: list[str] = []
    canonical_names: list[str] = []
    for raw_name in names:
        requested = str(raw_name).strip()
        if not requested:
            continue
        canonical = _SHEETS_READ_RANGE_ALIASES.get(
            requested.casefold(), requested
        )
        requested_names.append(requested)
        canonical_names.append(canonical)
        if canonical != requested:
            LOGGER.info(
                "sheets_read_named_ranges_alias requested=%s canonical=%s",
                requested,
                canonical,
            )

    payload = sheets_engine.read_named_ranges(
        spreadsheet_id,
        canonical_names,
        value_render_option=value_render_option,
    )

    enriched = dict(payload)
    for requested, canonical in zip(requested_names, canonical_names, strict=False):
        if requested in enriched:
            continue
        if canonical in payload:
            enriched[requested] = payload[canonical]
    return enriched


def _normalize_named_range_values(values: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for name, value in values.items():
        normalized[name] = _normalize_named_range_value(name=name, value=value)
    return normalized


def _validate_named_range_write_payload(values: dict[str, Any]) -> None:
    if not values:
        return
    normalized_names = [str(name).strip().lower() for name in values.keys()]
    read_only = [
        name
        for name in normalized_names
        if name in _SHEETS_RUNTIME_READ_ONLY_RANGES
    ]
    if read_only:
        raise ValueError(
            "Named-range write blocked for runtime read-only ranges: "
            f"{', '.join(sorted(set(read_only)))}."
        )
    has_story = any(name.startswith("story_") for name in normalized_names)
    has_comps = any(name.startswith("comps_") for name in normalized_names)
    if has_story and has_comps:
        raise ValueError(
            "Do not mix story_* and comps_* named-range writes in one call. "
            "Split into separate tool calls."
        )
    _validate_strict_named_range_semantics(values)


def _validate_strict_named_range_semantics(values: dict[str, Any]) -> None:
    for name, value in values.items():
        normalized_name = str(name or "").strip().lower()
        if normalized_name != "inp_tax_ttm":
            continue
        rate = _to_optional_rate_scalar(value)
        if rate is None:
            raise ValueError(
                "inp_tax_ttm must be numeric and expressed as a decimal effective tax rate "
                "(for example 0.19 or 19%)."
            )


def _drop_derived_control_range_writes(
    values: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    writable: dict[str, Any] = {}
    dropped: list[str] = []
    for name, value in values.items():
        normalized = str(name).strip().lower()
        if normalized in _COMPS_DERIVED_CONTROL_RANGES:
            dropped.append(str(name))
            continue
        writable[name] = value
    return writable, sorted(dropped)


def _normalize_named_range_value(*, name: str, value: Any) -> Any:
    normalized_name = str(name or "").strip().lower()
    numeric = _to_optional_numeric_scalar(value)
    if numeric is None:
        return value
    if normalized_name in _SHEETS_MONEY_MM_RANGES and abs(numeric) >= 1_000_000:
        normalized = numeric / 1_000_000
        LOGGER.info(
            "sheets_value_normalized range=%s rule=money_to_mm before=%s after=%s",
            name,
            numeric,
            normalized,
        )
        return normalized
    if normalized_name in _SHEETS_RATE_DECIMAL_RANGES and 1.0 < abs(numeric) <= 100.0:
        normalized = numeric / 100.0
        LOGGER.info(
            "sheets_value_normalized range=%s rule=percent_to_decimal before=%s after=%s",
            name,
            numeric,
            normalized,
        )
        return normalized
    return value


def _to_optional_numeric_scalar(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", "")
    if not text or text.startswith("="):
        return None
    if text.endswith("%"):
        try:
            return float(text[:-1])
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_optional_rate_scalar(value: Any) -> float | None:
    numeric = _to_optional_numeric_scalar(value)
    if numeric is None:
        return None
    if 1.0 < abs(numeric) <= 100.0:
        return numeric / 100.0
    return numeric


def _call_sheets_append_named_table_rows(
    *,
    sheets_engine: SheetsEngine,
    spreadsheet_id: str,
    table_name: str,
    rows: list[list[object]],
) -> dict[str, Any]:
    prepared_rows = _prepare_named_table_rows(table_name=table_name, rows=rows)
    _validate_named_table_rows(
        sheets_engine=sheets_engine,
        spreadsheet_id=spreadsheet_id,
        table_name=table_name,
        rows=prepared_rows,
        operation="append",
    )
    sheets_engine.append_named_table_rows(
        spreadsheet_id=spreadsheet_id,
        table_name=table_name,
        rows=prepared_rows,
    )
    return {"ok": True, "rows_appended": len(prepared_rows)}


def _call_sheets_write_named_table(
    *,
    sheets_engine: SheetsEngine,
    spreadsheet_id: str,
    table_name: str,
    rows: list[list[object]],
) -> dict[str, Any]:
    prepared_rows = _prepare_named_table_rows(table_name=table_name, rows=rows)
    _validate_named_table_rows(
        sheets_engine=sheets_engine,
        spreadsheet_id=spreadsheet_id,
        table_name=table_name,
        rows=prepared_rows,
        operation="write",
    )
    sheets_engine.write_named_table(
        spreadsheet_id=spreadsheet_id,
        table_name=table_name,
        rows=prepared_rows,
    )
    control_updates = _derive_comps_control_updates(
        table_name=table_name,
        rows=prepared_rows,
    )
    if control_updates:
        sheets_engine.write_named_ranges(
            spreadsheet_id=spreadsheet_id,
            values=control_updates,
        )
    return {
        "ok": True,
        "rows_written": len(prepared_rows),
        "control_ranges_written": len(control_updates),
    }


def _validate_named_table_rows(
    *,
    sheets_engine: SheetsEngine,
    spreadsheet_id: str,
    table_name: str,
    rows: list[list[object]],
    operation: str,
) -> None:
    normalized = table_name.strip().lower()
    if normalized == "sources_table":
        _validate_sources_table_rows(rows)
        return
    if normalized in _LOG_TABLE_SCHEMA_WIDTHS:
        _validate_log_table_rows(table_name=normalized, rows=rows)
        return
    if normalized in _COMPS_TABLE_NAMES:
        _validate_comps_table_rows(
            sheets_engine=sheets_engine,
            spreadsheet_id=spreadsheet_id,
            table_name=normalized,
            rows=rows,
            operation=operation,
        )
        return


def _prepare_named_table_rows(*, table_name: str, rows: list[list[object]]) -> list[list[object]]:
    normalized = table_name.strip().lower()
    if normalized == "sources_table":
        prepared = [_normalize_sources_row(row) for row in rows]
        return _strip_sources_header_rows(prepared)
    if normalized in _LOG_TABLE_SCHEMA_WIDTHS:
        width = _LOG_TABLE_SCHEMA_WIDTHS[normalized]
        return [_normalize_log_table_row(row, width=width) for row in rows]
    return [list(row) for row in rows]


def _normalize_sources_row(row: list[object]) -> list[object]:
    values = [_normalize_table_text_cell(cell) for cell in row]
    if len(values) == _SOURCES_TABLE_SCHEMA_WIDTH:
        values[4] = _normalize_source_as_of_date(values[4])
    return values


def _strip_sources_header_rows(rows: list[list[object]]) -> list[list[object]]:
    if rows and _is_sources_header_row(rows[0]):
        LOGGER.info(
            "sources_table_header_row_dropped reason=header_included_in_rows_payload"
        )
        return rows[1:]
    return rows


def _is_sources_header_row(row: list[object]) -> bool:
    if len(row) != _SOURCES_TABLE_SCHEMA_WIDTH:
        return False
    normalized = tuple(_normalize_table_text_cell(cell).casefold() for cell in row)
    return normalized == _SOURCES_TABLE_HEADER_ROW


def _normalize_log_table_row(row: list[object], *, width: int) -> list[object]:
    values = [_normalize_table_text_cell(cell) for cell in row]
    if len(values) > width:
        overflow = " | ".join(
            str(cell) for cell in values[width - 1 :] if str(cell).strip()
        )
        values = values[: width - 1] + [overflow]
    if len(values) < width:
        values.extend([""] * (width - len(values)))
    return values


def _normalize_table_text_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _normalize_source_as_of_date(value: object) -> str:
    text = _normalize_table_text_cell(value)
    if not text:
        return text
    try:
        serial = float(text)
    except ValueError:
        return text
    if serial < 20_000 or serial > 80_000:
        return text
    converted = date(1899, 12, 30) + timedelta(days=int(serial))
    return converted.isoformat()


def _validate_log_table_rows(*, table_name: str, rows: list[list[object]]) -> None:
    expected_width = _LOG_TABLE_SCHEMA_WIDTHS[table_name]
    required_columns = _LOG_TABLE_REQUIRED_COLUMN_INDEXES.get(table_name, ())
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            raise ValueError(
                f"{table_name} row {idx} must be a list with {expected_width} columns."
            )
        if len(row) != expected_width:
            raise ValueError(
                f"{table_name} rows must use fixed {expected_width}-column schema "
                f"(row={idx}, actual={len(row)})."
            )
        missing = [
            col_idx + 1
            for col_idx in required_columns
            if str(row[col_idx] if col_idx < len(row) else "").strip() == ""
        ]
        if missing:
            raise ValueError(
                f"{table_name} missing required fields (row={idx}, columns={missing})."
            )


def _validate_sources_table_rows(rows: list[list[object]]) -> None:
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            raise ValueError(
                f"sources_table row {idx} must be a list with {_SOURCES_TABLE_SCHEMA_WIDTH} columns."
            )
        if len(row) != _SOURCES_TABLE_SCHEMA_WIDTH:
            raise ValueError(
                "sources_table rows must use fixed 11-column schema "
                f"(row={idx}, expected={_SOURCES_TABLE_SCHEMA_WIDTH}, actual={len(row)})."
            )

        required_missing = [
            col_idx + 1
            for col_idx in _SOURCES_REQUIRED_COLUMN_INDEXES
            if str(row[col_idx] if col_idx < len(row) else "").strip() == ""
        ]
        if required_missing:
            raise ValueError(
                "sources_table missing required fields "
                f"(row={idx}, columns={required_missing})."
            )

        url = str(row[3]).strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(
                f"sources_table url must be absolute http(s) URL (row={idx}, value={url!r})."
            )
        as_of_date = str(row[4]).strip()
        if not _looks_like_iso_date_or_datetime(as_of_date):
            raise ValueError(
                "sources_table as_of_date must be ISO date/datetime "
                f"(row={idx}, value={as_of_date!r})."
            )


def _validate_comps_table_rows(
    *,
    sheets_engine: SheetsEngine,
    spreadsheet_id: str,
    table_name: str,
    rows: list[list[object]],
    operation: str,
) -> None:
    if operation != "write":
        raise ValueError(
            "Comps table updates must use sheets_write_named_table with table_name=comps_table_full."
        )
    if table_name != _COMPS_ALLOWED_WRITE_TABLE:
        raise ValueError(
            "Comps table must be written to table_name=comps_table_full to include header + data rows."
        )
    if len(rows) < 2:
        raise ValueError(
            "comps_table_full requires at least header row + one data row."
        )

    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            raise ValueError(f"comps_table_full row {idx} must be a list.")

    header = rows[0]
    last_idx = _last_non_empty_index(header)
    if last_idx < 2:
        raise ValueError(
            "comps_table_full header must include at least Ticker, one metric, and Notes."
        )

    first_header = str(header[0] if len(header) > 0 else "").strip().casefold()
    last_header = str(header[last_idx]).strip().casefold()
    if first_header != _COMPS_REQUIRED_HEADER_FIRST:
        raise ValueError(
            "comps_table_full header must start with 'Ticker' in column 1."
        )
    if last_header != _COMPS_REQUIRED_HEADER_LAST:
        raise ValueError(
            "comps_table_full header must end with 'Notes' as last non-empty header."
        )

    target_ticker = _read_target_ticker(
        sheets_engine=sheets_engine,
        spreadsheet_id=spreadsheet_id,
    )
    first_data_ticker = str(rows[1][0] if rows[1] else "").strip().upper()
    if not first_data_ticker:
        raise ValueError("comps_table_full first data row must include a ticker.")
    if target_ticker and first_data_ticker != target_ticker:
        raise ValueError(
            "comps_table_full first data row ticker must equal inp_ticker "
            f"({target_ticker}), found {first_data_ticker}."
        )

    for row_idx, row in enumerate(rows[1:], start=2):
        ticker = str(row[0] if row else "").strip()
        if not ticker:
            raise ValueError(
                f"comps_table_full missing ticker in data row {row_idx}."
            )
        notes = str(row[last_idx] if len(row) > last_idx else "").strip()
        if not notes:
            raise ValueError(
                f"comps_table_full missing Notes value in data row {row_idx}."
            )
        _validate_comps_note_quality(note=notes, row_idx=row_idx)


def _derive_comps_control_updates(
    *, table_name: str, rows: list[list[object]]
) -> dict[str, object]:
    normalized = table_name.strip().lower()
    if normalized != _COMPS_ALLOWED_WRITE_TABLE or not rows:
        return {}
    header = rows[0]
    last_idx = _last_non_empty_index(header)
    if last_idx < 1:
        return {}
    metric_count = 0
    for col_idx in range(1, last_idx):
        header_label = str(header[col_idx] if len(header) > col_idx else "").strip()
        if not header_label:
            continue
        if header_label.casefold() in _COMPS_NON_NUMERIC_HEADERS:
            continue
        metric_count += 1
    peer_count = 0
    for row in rows[1:]:
        ticker = str(row[0] if row else "").strip()
        if ticker:
            peer_count += 1
    return {
        "comps_peer_count": peer_count,
        "comps_multiple_count": metric_count,
    }


def _read_target_ticker(*, sheets_engine: SheetsEngine, spreadsheet_id: str) -> str:
    payload = sheets_engine.read_named_ranges(
        spreadsheet_id,
        ["inp_ticker"],
        value_render_option="UNFORMATTED_VALUE",
    )
    rows = payload.get("inp_ticker", [])
    if not rows or not rows[0]:
        return ""
    return str(rows[0][0]).strip().upper()


def _validate_comps_note_quality(*, note: str, row_idx: int) -> None:
    normalized = note.strip()
    if len(normalized) < _COMPS_ROW_NOTE_MIN_CHARS:
        raise ValueError(
            "comps_table_full Notes must be IB-grade and detailed "
            f"(row={row_idx}, min_chars={_COMPS_ROW_NOTE_MIN_CHARS})."
        )
    lowered = normalized.casefold()
    signal_count = sum(
        1 for token in _COMPS_ROW_NOTE_REQUIRED_SIGNALS if token in lowered
    )
    if signal_count < 3:
        raise ValueError(
            "comps_table_full Notes must include business model, execution quality, "
            f"and valuation-multiple rationale signals (row={row_idx})."
        )
    if normalized.count(".") < 2 and normalized.count(";") < 2:
        raise ValueError(
            "comps_table_full Notes must include a multi-part narrative "
            f"(row={row_idx})."
        )


def _looks_like_iso_date_or_datetime(value: str) -> bool:
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


def _last_non_empty_index(row: list[object]) -> int:
    last = -1
    for idx, value in enumerate(row):
        if str(value or "").strip():
            last = idx
    return last


def _call_sec_fundamentals(
    *, client: FundamentalsClient | None, ticker: str
) -> dict[str, Any]:
    if client is None:
        return {
            "error": "SEC fundamentals client not configured.",
            "fundamentals": None,
            "citations": [],
        }
    return {
        "fundamentals": client.fetch_company_fundamentals(ticker),
        "citations": client.fetch_citations(ticker),
    }


def _build_canonical_sheet_inputs(
    *, data_service: DataService, ticker: str
) -> dict[str, Any]:
    dataset = data_service.build_canonical_dataset(ticker)
    named_ranges = dataset.to_sheets_named_ranges()
    quality_report = _build_canonical_quality_report(named_ranges)
    artifact_path, artifact_sha256 = _persist_canonical_dataset_artifact(
        ticker=ticker,
        dataset=dataset,
        named_ranges=named_ranges,
        quality_report=quality_report,
    )
    return {
        "ticker": ticker,
        "named_ranges": named_ranges,
        "citations": dataset.citations,
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha256,
        "quality_report": quality_report,
    }


def _build_canonical_quality_report(named_ranges: dict[str, Any]) -> dict[str, Any]:
    missing_ranges = [
        name for name in _CANONICAL_QUALITY_REQUIRED_RANGES if name not in named_ranges
    ]
    null_ranges = [
        name
        for name in _CANONICAL_QUALITY_REQUIRED_RANGES
        if name in named_ranges and named_ranges.get(name) in (None, "")
    ]
    plausibility_issues = _canonical_plausibility_issues(named_ranges)
    is_complete = not missing_ranges and not null_ranges
    is_plausible = not plausibility_issues
    return {
        "required_count": len(_CANONICAL_QUALITY_REQUIRED_RANGES),
        "missing_ranges": missing_ranges,
        "null_ranges": null_ranges,
        "is_complete": is_complete,
        "is_plausible": is_plausible,
        "is_ready": is_complete and is_plausible,
        "plausibility_issues": plausibility_issues,
    }


def _canonical_plausibility_issues(named_ranges: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    numeric_values: dict[str, float] = {}
    for range_name, (lower, upper) in _CANONICAL_QUALITY_NUMERIC_BOUNDS.items():
        raw_value = named_ranges.get(range_name)
        numeric = _to_optional_numeric_scalar(raw_value)
        if numeric is None:
            continue
        numeric_values[range_name] = numeric
        if numeric < lower or numeric > upper:
            issues.append(
                f"{range_name} out of bounds ({numeric:.6f}; expected {lower}..{upper})."
            )

    revenue = numeric_values.get("inp_rev_ttm")
    ebit = numeric_values.get("inp_ebit_ttm")
    if revenue is not None and revenue <= 0:
        issues.append("inp_rev_ttm must be > 0.")
    if revenue is not None and ebit is not None and abs(ebit) > (abs(revenue) * 5.0):
        issues.append(
            "inp_ebit_ttm magnitude is implausible versus inp_rev_ttm "
            f"(ebit={ebit:.6f}, revenue={revenue:.6f})."
        )
    return issues


def _persist_canonical_dataset_artifact(
    *,
    ticker: str,
    dataset: Any,
    named_ranges: dict[str, Any],
    quality_report: dict[str, Any],
) -> tuple[str, str]:
    outdir = Path("artifacts") / "canonical_datasets"
    outdir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = outdir / f"{ticker.upper()}_canonical_dataset_{timestamp}.json"
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker.upper(),
        "canonical_dataset": _to_jsonable(dataset),
        "sheets_inputs": _to_jsonable(named_ranges),
        "sheets_input_completeness": quality_report,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    sha256 = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    payload["sha256"] = sha256
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path), sha256


def _dict_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _list_of_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            item_str = str(item).strip()
            if item_str:
                output.append(item_str)
        return output
    return []


def _list_of_rows(value: Any) -> list[list[object]]:
    if not isinstance(value, list):
        return []
    rows: list[list[object]] = []
    for row in value:
        if isinstance(row, list):
            rows.append(list(row))
        else:
            rows.append([row])
    return rows


def _coerce_optional_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    value_str = str(value).strip()
    if not value_str:
        return default
    try:
        return int(value_str)
    except ValueError:
        return default


def _coerce_optional_float(value: Any, *, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    value_str = str(value).strip()
    if not value_str:
        return default
    try:
        return float(value_str)
    except ValueError:
        return default


def _citations_or_empty(value: Any) -> list[DataSourceCitation]:
    if not isinstance(value, list):
        return []
    citations: list[DataSourceCitation] = []
    for row in value:
        if isinstance(row, DataSourceCitation):
            citations.append(row)
            continue
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "").strip()
        endpoint = str(row.get("endpoint") or "").strip()
        url = str(row.get("url") or "").strip()
        if not source:
            continue
        citations.append(
            DataSourceCitation(
                source=source,
                endpoint=endpoint,
                url=url,
                accessed_at_utc=datetime.now(timezone.utc),
                note=str(row.get("note") or ""),
            )
        )
    return citations


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value
