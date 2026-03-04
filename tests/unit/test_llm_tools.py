"""Unit tests for LLM tool-call registry wiring."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.app.tools.contracts import (
    CanonicalValuationDataset,
    CompanyFundamentals,
    MarketSnapshot,
    RatesSnapshot,
)
from backend.app.tools.llm_tools import build_phase_v1_tool_registry
from backend.app.tools.research_contracts import ResearchPacket


class _FakeSheetsEngine:
    def __init__(self) -> None:
        self.named_range_writes: list[tuple[str, dict[str, object]]] = []
        self.named_range_reads: list[tuple[str, list[str], str]] = []
        self.named_table_appends: list[tuple[str, str, list[list[object]]]] = []
        self.named_table_writes: list[tuple[str, str, list[list[object]]]] = []

    def copy_template(self, run_id: str, ticker: str) -> str:
        return f"{ticker}_{run_id}"

    def write_named_ranges(self, spreadsheet_id: str, values: dict[str, object]) -> None:
        self.named_range_writes.append((spreadsheet_id, values))

    def read_outputs(self, spreadsheet_id: str) -> dict[str, object]:
        return {"out_value_ps_weighted": 123.45, "spreadsheet_id": spreadsheet_id}

    def read_named_ranges(
        self,
        spreadsheet_id: str,
        names: list[str],
        *,
        value_render_option: str = "UNFORMATTED_VALUE",
    ) -> dict[str, list[list[object]]]:
        self.named_range_reads.append((spreadsheet_id, names, value_render_option))
        payload: dict[str, list[list[object]]] = {}
        for name in names:
            if name == "inp_ticker":
                payload[name] = [["AAPL"]]
            else:
                payload[name] = [[spreadsheet_id]]
        return payload

    def append_named_table_rows(
        self,
        spreadsheet_id: str,
        table_name: str,
        rows: list[list[object]],
    ) -> None:
        self.named_table_appends.append((spreadsheet_id, table_name, rows))

    def write_named_table(
        self,
        spreadsheet_id: str,
        table_name: str,
        rows: list[list[object]],
    ) -> None:
        self.named_table_writes.append((spreadsheet_id, table_name, rows))

    def append_logbook_run(self, summary_row: list[object]) -> None:
        del summary_row


class _FakeDataService:
    def build_canonical_dataset(self, ticker: str) -> CanonicalValuationDataset:
        now = datetime.now(timezone.utc)
        return CanonicalValuationDataset(
            ticker=ticker,
            fundamentals=CompanyFundamentals(
                ticker=ticker,
                company_name="Example Corp",
                currency="USD",
                revenue_ttm=100.0,
                ebit_ttm=20.0,
                tax_rate_ttm=0.2,
                da_ttm=3.0,
                capex_ttm=4.0,
                delta_nwc_ttm=1.0,
                rd_ttm=2.0,
                rent_ttm=1.0,
                cash=10.0,
                debt=15.0,
                basic_shares=50.0,
                diluted_shares=52.0,
            ),
            market=MarketSnapshot(
                ticker=ticker,
                price=100.0,
                beta=1.1,
                market_cap=5000.0,
                shares_outstanding=50.0,
                captured_at_utc=now,
            ),
            rates=RatesSnapshot(
                risk_free_rate=0.04,
                equity_risk_premium=0.05,
                cost_of_debt=0.055,
                debt_weight=0.1,
                captured_at_utc=now,
            ),
        )


class _FakeResearchService:
    def build_research_packet(self, ticker: str, facts: dict, news_limit: int) -> ResearchPacket:
        del facts
        del news_limit
        return ResearchPacket(ticker=ticker)


def test_llm_tool_registry_calls_canonical_dataset_tool() -> None:
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=None,
    )

    result = registry.call("fetch_canonical_dataset", {"ticker": "AAPL"})

    assert "result" in result
    assert result["result"]["ticker"] == "AAPL"
    assert result["result"]["fundamentals"]["company_name"] == "Example Corp"


def test_llm_tool_registry_validates_required_fields() -> None:
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=None,
    )

    try:
        registry.call("fetch_canonical_dataset", {})
    except ValueError as exc:
        assert "missing required fields" in str(exc)
    else:  # pragma: no cover - defensive check
        raise AssertionError("Expected ValueError for missing required fields")


def test_named_table_tool_schemas_define_nested_row_items_for_gemini() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    append_schema = registry.spec("sheets_append_named_table_rows").input_schema
    write_schema = registry.spec("sheets_write_named_table").input_schema

    append_rows = append_schema["properties"]["rows"]
    write_rows = write_schema["properties"]["rows"]

    assert append_rows["type"] == "array"
    assert append_rows["items"]["type"] == "array"
    assert append_rows["items"]["items"]["type"] == "string"

    assert write_rows["type"] == "array"
    assert write_rows["items"]["type"] == "array"
    assert write_rows["items"]["items"]["type"] == "string"


def test_llm_tool_registry_supports_named_sheet_tools() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    write_result = registry.call(
        "sheets_write_named_ranges",
        {
            "spreadsheet_id": "abc123",
            "values": {"inp_ticker": "AAPL"},
        },
    )
    read_result = registry.call(
        "sheets_read_named_ranges",
        {
            "spreadsheet_id": "abc123",
            "names": ["inp_ticker", "out_value_ps_weighted"],
        },
    )
    append_result = registry.call(
        "sheets_append_named_table_rows",
        {
            "spreadsheet_id": "abc123",
            "table_name": "log_actions_table",
            "rows": [["phase", "action", "step completed"]],
        },
    )
    table_result = registry.call(
        "sheets_write_named_table",
        {
            "spreadsheet_id": "abc123",
            "table_name": "sources_table",
            "rows": [
                [
                    "inputs_ttm",
                    "SEC EDGAR",
                    "Company Facts",
                    "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    "2026-02-16",
                    "Primary filing source.",
                    "revenue_ttm",
                    "100.0",
                    "USDm",
                    "ttm_rollup",
                    "SRC-SEC-1",
                ]
            ],
        },
    )

    assert write_result["ok"] is True
    assert sheets.named_range_writes[0][0] == "abc123"
    assert "result" in read_result
    assert "inp_ticker" in read_result["result"]
    assert append_result["ok"] is True
    assert table_result["ok"] is True
    assert sheets.named_table_appends[0][1] == "log_actions_table"
    assert sheets.named_table_writes[0][1] == "sources_table"


def test_llm_tool_registry_rejects_unknown_named_range_aliases_on_read() -> None:
    class _StrictFakeSheetsEngine(_FakeSheetsEngine):
        _KNOWN = {
            "inp_ticker",
            "inp_name",
            "inp_px",
            "inp_rf",
            "inp_erp",
            "inp_beta",
            "inp_cash",
            "inp_debt",
            "inp_basic_shares",
        }

        def read_named_ranges(
            self,
            spreadsheet_id: str,
            names: list[str],
            *,
            value_render_option: str = "UNFORMATTED_VALUE",
        ) -> dict[str, list[list[object]]]:
            unknown = [name for name in names if name not in self._KNOWN]
            if unknown:
                raise ValueError(
                    "Unknown named ranges for read_named_ranges: "
                    + ", ".join(sorted(unknown))
                )
            return super().read_named_ranges(
                spreadsheet_id,
                names,
                value_render_option=value_render_option,
            )

    sheets = _StrictFakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    with pytest.raises(ValueError, match="Unknown named ranges for read_named_ranges"):
        registry.call(
            "sheets_read_named_ranges",
            {
                "spreadsheet_id": "abc123",
                "names": ["inp_base_growth_legacy", "inp_base_margin_legacy", "inp_ticker"],
            },
        )


def test_llm_tool_registry_normalizes_sheet_units_before_write() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    result = registry.call(
        "sheets_write_named_ranges",
        {
            "spreadsheet_id": "abc123",
            "values": {
                "inp_rev_ttm": 130_497_000_000,
                "inp_ebit_ttm": "81453000000",
                "inp_basic_shares": 24_477_000_000,
                "inp_rf": 4.25,
                "inp_w_base": "60",
                "inp_ticker": "NVDA",
            },
        },
    )

    assert result["ok"] is True
    written = sheets.named_range_writes[-1][1]
    assert written["inp_rev_ttm"] == 130_497.0
    assert written["inp_ebit_ttm"] == 81_453.0
    assert written["inp_basic_shares"] == 24_477.0
    assert written["inp_rf"] == 0.0425
    assert written["inp_w_base"] == 0.6
    assert written["inp_ticker"] == "NVDA"


def test_llm_tool_registry_normalizes_percent_tax_rate_before_write() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    result = registry.call(
        "sheets_write_named_ranges",
        {
            "spreadsheet_id": "abc123",
            "values": {
                "inp_tax_ttm": "19.6%",
            },
        },
    )

    assert result["ok"] is True
    written = sheets.named_range_writes[-1][1]
    assert written["inp_tax_ttm"] == pytest.approx(0.196)


def test_llm_tool_registry_accepts_unbounded_numeric_tax_rate_for_tax_field() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    result = registry.call(
        "sheets_write_named_ranges",
        {
            "spreadsheet_id": "abc123",
            "values": {
                "inp_tax_ttm": "15675100000",
            },
        },
    )

    assert result["ok"] is True
    written = sheets.named_range_writes[-1][1]
    assert written["inp_tax_ttm"] == "15675100000"


def test_llm_tool_registry_drops_direct_comps_control_writes() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    result = registry.call(
        "sheets_write_named_ranges",
        {
            "spreadsheet_id": "abc123",
            "values": {
                "comps_peer_count": 6,
                "comps_multiple_count": 4,
            },
        },
    )

    assert result["ok"] is True
    assert result["dropped_ranges"] == ["comps_multiple_count", "comps_peer_count"]
    assert result["written_ranges"] == 0
    assert sheets.named_range_writes == []


def test_llm_tool_registry_rejects_story_and_comps_write_mix() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    with pytest.raises(ValueError, match="Do not mix story_\\* and comps_\\*"):
        registry.call(
            "sheets_write_named_ranges",
            {
                "spreadsheet_id": "abc123",
                "values": {
                    "story_thesis": "Narrative text",
                    "comps_peer_count": 6,
                },
            },
        )


def test_llm_tool_registry_rejects_runtime_read_only_story_header_write() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    with pytest.raises(ValueError, match="runtime read-only ranges"):
        registry.call(
            "sheets_write_named_ranges",
            {
                "spreadsheet_id": "abc123",
                "values": {
                    "story_grid_header": [["Scenario", "Core narrative"]],
                },
            },
        )


def test_llm_tool_registry_rejects_runtime_status_writes() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    with pytest.raises(ValueError, match="runtime read-only ranges"):
        registry.call(
            "sheets_write_named_ranges",
            {
                "spreadsheet_id": "abc123",
                "values": {
                    "log_status": "COMPLETED",
                    "log_end_ts": "2026-02-20T00:00:00Z",
                },
            },
        )


def test_llm_tool_registry_rejects_malformed_sources_table_schema() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    try:
        registry.call(
            "sheets_append_named_table_rows",
            {
                "spreadsheet_id": "abc123",
                "table_name": "sources_table",
                "rows": [["bad", "shape"]],
            },
        )
    except ValueError as exc:
        assert "fixed 11-column schema" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for malformed sources_table row")


def test_llm_tool_registry_strips_sources_header_row_on_write() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    result = registry.call(
        "sheets_write_named_table",
        {
            "spreadsheet_id": "abc123",
            "table_name": "sources_table",
            "rows": [
                [
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
                ],
                [
                    "inputs_ttm",
                    "SEC EDGAR",
                    "Company Facts",
                    "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    "2026-02-16",
                    "Primary filing source.",
                    "revenue_ttm",
                    "100.0",
                    "USDm",
                    "ttm_rollup",
                    "SRC-SEC-1",
                ],
            ],
        },
    )

    assert result["ok"] is True
    written_rows = sheets.named_table_writes[-1][2]
    assert len(written_rows) == 1
    assert written_rows[0][0] == "inputs_ttm"


def test_llm_tool_registry_rejects_comps_append_operations() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    try:
        registry.call(
            "sheets_append_named_table_rows",
            {
                "spreadsheet_id": "abc123",
                "table_name": "comps_table_full",
                "rows": [["Ticker", "EV/Sales", "Notes"]],
            },
        )
    except ValueError as exc:
        assert "must use sheets_write_named_table" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for comps append")


def test_llm_tool_registry_writes_comps_table_full_and_updates_control_ranges() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    result = registry.call(
        "sheets_write_named_table",
        {
            "spreadsheet_id": "abc123",
            "table_name": "comps_table_full",
            "rows": [
                ["Ticker", "EV/Sales", "EV/EBIT", "Notes"],
                [
                    "AAPL",
                    "6.1",
                    "22.4",
                    (
                        "Business model: diversified consumer hardware and services platform "
                        "with recurring ecosystem monetization. Execution: sustained gross-margin "
                        "discipline, buyback cadence, and premium product refresh consistency. "
                        "Valuation multiple rationale: premium multiple supported by mix quality "
                        "and capital-return durability versus large-cap peers."
                    ),
                ],
                [
                    "MSFT",
                    "11.2",
                    "27.0",
                    (
                        "Business model: enterprise software and cloud platform with high switching "
                        "costs and mission-critical workloads. Execution: durable cloud growth, "
                        "margin resilience, and disciplined product bundling across segments. "
                        "Valuation multiple rationale: premium multiple justified by superior "
                        "recurring revenue quality and operating leverage."
                    ),
                ],
                [
                    "GOOGL",
                    "7.6",
                    "20.8",
                    (
                        "Business model: advertising ecosystem plus scaled cloud platform with "
                        "network effects across search, video, and distribution. Execution: "
                        "improving cost controls while reinvesting in AI and cloud capacity. "
                        "Valuation multiple rationale: relative discount to software leaders "
                        "reflects ad cyclicality but supported by cash generation."
                    ),
                ],
            ],
        },
    )

    assert result["ok"] is True
    assert result["control_ranges_written"] == 2
    assert sheets.named_table_writes[-1][1] == "comps_table_full"
    assert sheets.named_range_writes[-1][1]["comps_peer_count"] == 3
    assert sheets.named_range_writes[-1][1]["comps_multiple_count"] == 2


def test_llm_tool_registry_normalizes_overwide_log_rows() -> None:
    sheets = _FakeSheetsEngine()
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=sheets,
    )

    result = registry.call(
        "sheets_append_named_table_rows",
        {
            "spreadsheet_id": "abc123",
            "table_name": "log_actions_table",
            "rows": [
                [
                    "memo",
                    "action",
                    "Memo composed and story narrative updated.",
                    "N/A",
                    "2026-02-17T00:10:00Z",
                    "Finalized investment memo for WMT.",
                    "out_value_ps_weighted",
                    "89.11",
                    "USD",
                    "extra_col_1",
                    "extra_col_2",
                ]
            ],
        },
    )

    assert result["ok"] is True
    normalized_row = sheets.named_table_appends[-1][2][0]
    assert len(normalized_row) == 9
    assert "extra_col_1" in normalized_row[-1]
    assert "extra_col_2" in normalized_row[-1]


def test_llm_tool_registry_canonical_sheet_inputs_include_tsm_prefill() -> None:
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=None,
    )

    result = registry.call("fetch_canonical_sheet_inputs", {"ticker": "AAPL"})
    named_ranges = result["result"]["named_ranges"]

    assert "inp_tsm_tranche1_count_mm" in named_ranges
    assert named_ranges["inp_tsm_tranche1_type"] == "RSU"
    assert result["result"]["artifact_path"].startswith("artifacts/canonical_datasets/")
    assert len(result["result"]["artifact_sha256"]) == 64
    assert result["result"]["quality_report"]["is_complete"] is True
    artifact_path = Path(result["result"]["artifact_path"])
    if artifact_path.exists():
        artifact_path.unlink()


class _ImplausibleDataService(_FakeDataService):
    def build_canonical_dataset(self, ticker: str) -> CanonicalValuationDataset:
        dataset = super().build_canonical_dataset(ticker)
        market = dataset.market
        return CanonicalValuationDataset(
            ticker=dataset.ticker,
            fundamentals=dataset.fundamentals,
            market=MarketSnapshot(
                ticker=market.ticker,
                price=-5.0,
                beta=market.beta,
                market_cap=market.market_cap,
                shares_outstanding=market.shares_outstanding,
                captured_at_utc=market.captured_at_utc,
            ),
            rates=dataset.rates,
            news=list(dataset.news),
            citations=list(dataset.citations),
            assumptions=dict(dataset.assumptions),
            tsm=dataset.tsm,
        )


class _OutOfBoundsBetaDataService(_FakeDataService):
    def build_canonical_dataset(self, ticker: str) -> CanonicalValuationDataset:
        dataset = super().build_canonical_dataset(ticker)
        market = dataset.market
        return CanonicalValuationDataset(
            ticker=dataset.ticker,
            fundamentals=dataset.fundamentals,
            market=MarketSnapshot(
                ticker=market.ticker,
                price=market.price,
                beta=-0.25,
                market_cap=market.market_cap,
                shares_outstanding=market.shares_outstanding,
                captured_at_utc=market.captured_at_utc,
            ),
            rates=dataset.rates,
            news=list(dataset.news),
            citations=list(dataset.citations),
            assumptions=dict(dataset.assumptions),
            tsm=dataset.tsm,
        )


def test_llm_tool_registry_canonical_sheet_inputs_flags_implausible_values() -> None:
    registry = build_phase_v1_tool_registry(
        data_service=_ImplausibleDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=None,
    )

    result = registry.call("fetch_canonical_sheet_inputs", {"ticker": "AAPL"})
    quality = result["result"]["quality_report"]

    assert quality["is_complete"] is True
    assert quality["is_plausible"] is False
    assert quality["is_ready"] is False
    assert any("inp_px out of bounds" in issue for issue in quality["plausibility_issues"])
    artifact_path = Path(result["result"]["artifact_path"])
    if artifact_path.exists():
        artifact_path.unlink()


def test_llm_tool_registry_canonical_sheet_inputs_falls_back_invalid_beta() -> None:
    registry = build_phase_v1_tool_registry(
        data_service=_OutOfBoundsBetaDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=None,
    )

    result = registry.call("fetch_canonical_sheet_inputs", {"ticker": "AAPL"})
    named_ranges = result["result"]["named_ranges"]
    quality = result["result"]["quality_report"]

    assert named_ranges["inp_beta"] == pytest.approx(1.0)
    assert quality["is_complete"] is True
    assert quality["is_plausible"] is True
    assert quality["is_ready"] is True
    assert not any("inp_beta out of bounds" in issue for issue in quality["plausibility_issues"])
    artifact_path = Path(result["result"]["artifact_path"])
    if artifact_path.exists():
        artifact_path.unlink()


def test_llm_tool_registry_includes_sec_tool_even_without_client() -> None:
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=None,
    )

    result = registry.call("fetch_sec_filing_fundamentals", {"ticker": "AAPL"})

    assert "result" in result
    assert result["result"]["error"] == "SEC fundamentals client not configured."


def test_llm_tool_registry_executes_python_math_tool() -> None:
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=None,
    )

    result = registry.call(
        "python_execute_math",
        {
            "code": (
                "import math\n"
                "def compute(inputs):\n"
                "    values = inputs.get('values', [])\n"
                "    print('values_count', len(values))\n"
                "    return {'total': sum(values), 'sqrt_total': math.sqrt(sum(values))}\n"
            ),
            "inputs": {"values": [2, 3, 5]},
        },
    )

    assert "result" in result
    assert result["result"]["output"]["total"] == 10
    assert result["result"]["output"]["sqrt_total"] == 10 ** 0.5
    assert "values_count 3" in result["result"]["stdout"]
    assert result["result"]["stderr"] == ""
    assert result["result"]["exit_code"] == 0
    assert "code_hash" in result["result"]


def test_llm_tool_registry_executes_python_math_with_numpy() -> None:
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=None,
    )

    result = registry.call(
        "python_execute_math",
        {
            "code": (
                "import numpy as np\n"
                "def compute(inputs):\n"
                "    values = np.array(inputs.get('values', []), dtype=float)\n"
                "    print('numpy_mean', float(values.mean()))\n"
                "    return {'mean': float(values.mean()), 'std': float(values.std())}\n"
            ),
            "inputs": {"values": [10, 20, 30, 40]},
        },
    )

    assert "result" in result
    assert result["result"]["output"]["mean"] == 25.0
    assert result["result"]["output"]["std"] > 0.0
    assert "numpy_mean 25.0" in result["result"]["stdout"]
    assert result["result"]["exit_code"] == 0


def test_llm_tool_registry_python_math_allows_isinstance() -> None:
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=None,
    )

    result = registry.call(
        "python_execute_math",
        {
            "code": (
                "def compute(inputs):\n"
                "    value = inputs.get('value')\n"
                "    print('is_str', isinstance(value, str))\n"
                "    return {'is_str': isinstance(value, str)}\n"
            ),
            "inputs": {"value": "GOOG"},
        },
    )

    assert result["result"]["output"]["is_str"] is True
    assert "is_str True" in result["result"]["stdout"]
    assert result["result"]["exit_code"] == 0


class _FailingResearchService:
    def build_research_packet(self, ticker: str, facts: dict, news_limit: int) -> ResearchPacket:
        del ticker, facts, news_limit
        raise RuntimeError("provider unavailable")


def test_llm_tool_registry_degrades_transient_research_tool_failures() -> None:
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FailingResearchService(),
        sheets_engine=None,
    )

    result = registry.call("fetch_research_packet", {"ticker": "AAPL"})

    assert "result" in result
    assert result["result"]["error"] == "provider_degraded"
    assert result["result"]["tool"] == "fetch_research_packet"


def test_llm_tool_registry_python_math_surfaces_stderr_on_failure() -> None:
    registry = build_phase_v1_tool_registry(
        data_service=_FakeDataService(),
        research_service=_FakeResearchService(),
        sheets_engine=None,
    )

    try:
        registry.call(
            "python_execute_math",
            {
                "code": (
                    "def compute(inputs):\n"
                    "    print('before boom')\n"
                    "    raise ValueError('boom')\n"
                ),
                "inputs": {},
            },
        )
    except RuntimeError as exc:
        message = str(exc)
        assert "ValueError: boom" in message
        assert "STDERR:" in message
        assert "before boom" in message
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected RuntimeError from python_execute_math failure")
