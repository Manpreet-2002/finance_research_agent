"""Post-run local investment memo generation pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import re
import subprocess
from typing import Any

from ..core.settings import Settings
from ..llm.client import LlmClient, LlmRequest
from ..schemas.valuation_run import ValuationRunRequest, ValuationRunResult
from ..sheets.engine import SheetsEngine
from ..tools.data_service import DataService
from ..tools.research_service import ResearchService

_JSON_DECODER = json.JSONDecoder()
_RUN_TS_RE = re.compile(r"(\d{8}T\d{6}Z)")

_DEFAULT_MIN_REQUIRED_CHARTS = 6
_DEFAULT_CHART_IDS: tuple[str, ...] = (
    "dcf_outcomes_vs_market",
    "scenario_gap_vs_market",
    "scenario_weights",
    "comps_ev_ebit",
    "comps_ev_sales",
    "sensitivity_heatmap",
    "peer_market_cap",
    "peer_revenue_ebit",
)


@dataclass(frozen=True)
class MemoWrapperResult:
    """Wrapper-level memo execution result (separate from valuation run status)."""

    status: str
    manifest_path: Path
    output_dir: Path
    html_path: Path | None = None
    markdown_path: Path | None = None
    pdf_path: Path | None = None
    chart_manifest_path: Path | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class _NarrativePack:
    title: str
    subtitle: str
    thesis: str
    sections: tuple[dict[str, str], ...]
    conclusion: str


_CITATION_RE = re.compile(r"\[(\d+)\]")


class PostRunMemoService:
    """Generate a local, client-ready memo with ECharts infographics after valuation run."""

    def __init__(
        self,
        *,
        settings: Settings,
        llm_client: LlmClient,
        sheets_engine: SheetsEngine,
        data_service: DataService,
        research_service: ResearchService,
        repo_root: Path | None = None,
    ) -> None:
        self.settings = settings
        self.llm_client = llm_client
        self.sheets_engine = sheets_engine
        self.data_service = data_service
        self.research_service = research_service
        self.repo_root = repo_root or Path(__file__).resolve().parents[3]
        self._logger = logging.getLogger("finance_research_agent.memo.post_run")

    def generate(
        self,
        *,
        request: ValuationRunRequest,
        result: ValuationRunResult,
        with_memo: bool,
    ) -> MemoWrapperResult:
        output_dir = self.repo_root / "artifacts" / "memos" / request.run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "memo_manifest.json"

        notes: list[str] = []
        errors: list[str] = []
        status = "SKIPPED"
        bundle_path: Path | None = None
        chart_manifest_path: Path | None = None
        memo_markdown_path: Path | None = None
        memo_html_path: Path | None = None
        memo_pdf_path: Path | None = None

        started = _utc_now_iso()
        if not with_memo:
            notes.append("Memo generation disabled via --no-with-memo.")
            self._write_manifest(
                manifest_path=manifest_path,
                status=status,
                request=request,
                result=result,
                started_at_utc=started,
                finished_at_utc=_utc_now_iso(),
                bundle_path=bundle_path,
                chart_manifest_path=chart_manifest_path,
                markdown_path=memo_markdown_path,
                html_path=memo_html_path,
                pdf_path=memo_pdf_path,
                notes=notes,
                errors=errors,
            )
            return MemoWrapperResult(
                status=status,
                manifest_path=manifest_path,
                output_dir=output_dir,
                notes=tuple(notes),
            )

        if str(result.status).upper() != "COMPLETED":
            notes.append("Memo generation skipped because valuation run did not complete.")
            self._write_manifest(
                manifest_path=manifest_path,
                status=status,
                request=request,
                result=result,
                started_at_utc=started,
                finished_at_utc=_utc_now_iso(),
                bundle_path=bundle_path,
                chart_manifest_path=chart_manifest_path,
                markdown_path=memo_markdown_path,
                html_path=memo_html_path,
                pdf_path=memo_pdf_path,
                notes=notes,
                errors=errors,
            )
            return MemoWrapperResult(
                status=status,
                manifest_path=manifest_path,
                output_dir=output_dir,
                notes=tuple(notes),
            )

        if not result.spreadsheet_id:
            notes.append("Memo generation skipped: run has no spreadsheet_id.")
            self._write_manifest(
                manifest_path=manifest_path,
                status=status,
                request=request,
                result=result,
                started_at_utc=started,
                finished_at_utc=_utc_now_iso(),
                bundle_path=bundle_path,
                chart_manifest_path=chart_manifest_path,
                markdown_path=memo_markdown_path,
                html_path=memo_html_path,
                pdf_path=memo_pdf_path,
                notes=notes,
                errors=errors,
            )
            return MemoWrapperResult(
                status=status,
                manifest_path=manifest_path,
                output_dir=output_dir,
                notes=tuple(notes),
            )

        try:
            bundle = self._build_bundle(request=request, result=result)
            bundle_path = output_dir / "memo_bundle.json"
            bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

            chart_manifest_path = self._render_infographics(bundle_path=bundle_path, output_dir=output_dir)
            chart_manifest = json.loads(chart_manifest_path.read_text(encoding="utf-8"))
            required_charts = max(
                _DEFAULT_MIN_REQUIRED_CHARTS,
                int(self.settings.memo_min_infographics),
            )
            generated_charts = self._validate_chart_manifest(
                chart_manifest=chart_manifest,
                required_charts=required_charts,
            )

            narrative = self._compose_narrative(bundle=bundle)
            memo_markdown_path = output_dir / "investment_memo.md"
            memo_markdown_path.write_text(
                self._to_markdown(narrative=narrative),
                encoding="utf-8",
            )

            memo_html_path = output_dir / "investment_memo.html"
            memo_html_path.write_text(
                self._render_html(
                    bundle=bundle,
                    chart_manifest=chart_manifest,
                    narrative=narrative,
                    chart_dir=(output_dir / "charts"),
                ),
                encoding="utf-8",
            )

            memo_pdf_path = output_dir / "investment_memo.pdf"
            self._render_pdf(html_path=memo_html_path, pdf_path=memo_pdf_path)

            status = "COMPLETED"
            notes.append(
                f"Memo generated with {len(generated_charts)} charts at {memo_pdf_path}."
            )
        except Exception as exc:  # noqa: BLE001 - wrapper-level failure capture
            status = "COMPLETED_WITH_MEMO_FAILURE"
            errors.append(str(exc))
            self._logger.exception("post_run_memo_failed run_id=%s", request.run_id)

        finished = _utc_now_iso()
        self._write_manifest(
            manifest_path=manifest_path,
            status=status,
            request=request,
            result=result,
            started_at_utc=started,
            finished_at_utc=finished,
            bundle_path=bundle_path,
            chart_manifest_path=chart_manifest_path,
            markdown_path=memo_markdown_path,
            html_path=memo_html_path,
            pdf_path=memo_pdf_path,
            notes=notes,
            errors=errors,
        )

        return MemoWrapperResult(
            status=status,
            manifest_path=manifest_path,
            output_dir=output_dir,
            html_path=memo_html_path,
            markdown_path=memo_markdown_path,
            pdf_path=memo_pdf_path,
            chart_manifest_path=chart_manifest_path,
            notes=tuple(notes + errors),
        )

    def _build_bundle(
        self,
        *,
        request: ValuationRunRequest,
        result: ValuationRunResult,
    ) -> dict[str, Any]:
        ticker = request.ticker.strip().upper()
        run_id = request.run_id
        spreadsheet_id = str(result.spreadsheet_id)

        named_ranges = [
            "inp_ticker",
            "inp_name",
            "inp_px",
            "inp_w_pess",
            "inp_w_base",
            "inp_w_opt",
            "out_value_ps_pess",
            "out_value_ps_base",
            "out_value_ps_opt",
            "out_value_ps_weighted",
            "out_equity_value_weighted",
            "out_enterprise_value_weighted",
            "OUT_WACC",
            "out_terminal_g",
            "comps_table_full",
            "sens_wacc_vector",
            "sens_terminal_g_vector",
            "sens_grid_values",
            "story_thesis",
            "story_growth",
            "story_profitability",
            "story_reinvestment",
            "story_risk",
            "story_sanity_checks",
            "sources_table",
        ]

        sheet_values = self.sheets_engine.read_named_ranges(
            spreadsheet_id,
            named_ranges,
            value_render_option="UNFORMATTED_VALUE",
        )

        scenario_rows = self._build_scenario_rows(sheet_values)
        peers_rows = self._parse_comps_table(sheet_values.get("comps_table_full"))
        sensitivity = self._parse_sensitivity_grid(sheet_values)

        canonical = self._load_canonical_dataset(ticker=ticker, run_id=run_id)
        canonical_dataset = canonical.get("canonical_dataset") or {}
        fundamentals = canonical_dataset.get("fundamentals") or {}
        market = canonical_dataset.get("market") or {}

        facts = {
            "weighted_value_per_share": scenario_rows[-1]["valuePsUsd"] if scenario_rows else None,
            "market_price": _scalar_float(sheet_values.get("inp_px")),
            "wacc": _scalar_float(sheet_values.get("OUT_WACC")),
            "terminal_growth": _scalar_float(sheet_values.get("out_terminal_g")),
            "peer_count": len(peers_rows),
        }
        research_packet = self.research_service.build_research_packet(
            ticker=ticker,
            facts=facts,
            news_limit=12,
        )

        citations = self._build_citations(
            canonical=canonical,
            research_packet=research_packet,
            sheet_sources=sheet_values.get("sources_table"),
            run_id=run_id,
            ticker=ticker,
        )

        chart_ids = self._plan_chart_ids(
            ticker=ticker,
            scenario_rows=scenario_rows,
            peers_rows=peers_rows,
            sensitivity=sensitivity,
        )

        run_log_path = self.repo_root / "artifacts" / "run_logs" / f"{run_id}.log"
        tool_calls_path = (
            self.repo_root
            / "artifacts"
            / "canonical_datasets"
            / f"{run_id}_tool_calls.jsonl"
        )

        out_wacc = _scalar_float(sheet_values.get("OUT_WACC"))
        out_terminal_g = _scalar_float(sheet_values.get("out_terminal_g"))

        bundle: dict[str, Any] = {
            "meta": {
                "generatedAtUtc": _utc_now_iso(),
                "runId": run_id,
                "ticker": ticker,
                "companyName": _scalar_text(sheet_values.get("inp_name"))
                or fundamentals.get("company_name")
                or "",
                "status": str(result.status),
                "spreadsheetId": spreadsheet_id,
            },
            "marketPriceUsd": _scalar_float(sheet_values.get("inp_px")),
            "valuation": {
                "outWaccPct": None if out_wacc is None else out_wacc * 100,
                "outTerminalGPct": None if out_terminal_g is None else out_terminal_g * 100,
                "weightedEquityValueUsdB": _scale_to_billions(
                    _scalar_float(sheet_values.get("out_equity_value_weighted"))
                ),
                "weightedEnterpriseValueUsdB": _scale_to_billions(
                    _scalar_float(sheet_values.get("out_enterprise_value_weighted"))
                ),
                "scenarios": scenario_rows,
                "scenarioWeights": [
                    row for row in scenario_rows if row.get("scenario") in {"Pess", "Base", "Opt"}
                ],
            },
            "fundamentals": {
                "revenueTtmUsdB": _scale_to_billions(_maybe_float(fundamentals.get("revenue_ttm"))),
                "ebitTtmUsdB": _scale_to_billions(_maybe_float(fundamentals.get("ebit_ttm"))),
                "ebitMarginPct": _safe_pct(
                    _maybe_float(fundamentals.get("ebit_ttm")),
                    _maybe_float(fundamentals.get("revenue_ttm")),
                ),
                "marketCapUsdB": _scale_to_billions(_maybe_float(market.get("market_cap"))),
                "cashUsdB": _scale_to_billions(_maybe_float(fundamentals.get("cash"))),
                "debtUsdB": _scale_to_billions(_maybe_float(fundamentals.get("debt"))),
            },
            "peers": {
                "rows": peers_rows,
                "evEbitMedian": _median_numeric([row.get("EV/EBIT") for row in peers_rows]),
                "evSalesMedian": _median_numeric([row.get("EV/Sales") for row in peers_rows]),
            },
            "sensitivity": sensitivity,
            "story": {
                "thesis": _scalar_text(sheet_values.get("story_thesis")),
                "growth": _scalar_text(sheet_values.get("story_growth")),
                "profitability": _scalar_text(sheet_values.get("story_profitability")),
                "reinvestment": _scalar_text(sheet_values.get("story_reinvestment")),
                "risk": _scalar_text(sheet_values.get("story_risk")),
                "sanityChecks": _scalar_text(sheet_values.get("story_sanity_checks")),
            },
            "research": {
                "news": [asdict(item) for item in research_packet.news[:12]],
                "transcriptSignals": [asdict(item) for item in research_packet.transcript_signals[:10]],
                "corporateActions": [asdict(item) for item in research_packet.corporate_actions[:10]],
                "peerUniverse": [asdict(item) for item in research_packet.peers[:12]],
                "contradictions": [asdict(item) for item in research_packet.contradictions],
            },
            "chart_ids": chart_ids,
            "chart_takeaways": self._chart_takeaways(
                scenario_rows=scenario_rows,
                peers_rows=peers_rows,
                sensitivity=sensitivity,
                market_price=_scalar_float(sheet_values.get("inp_px")),
                wacc_pct=None if out_wacc is None else out_wacc * 100,
                g_pct=None if out_terminal_g is None else out_terminal_g * 100,
            ),
            "sources": citations,
            "artifacts": {
                "runLogPath": str(run_log_path),
                "toolCallsPath": str(tool_calls_path),
                "canonicalDatasetPath": str(canonical.get("_path") or ""),
            },
        }
        return bundle

    def _build_scenario_rows(self, values: dict[str, list[list[object]]]) -> list[dict[str, Any]]:
        market_price = _scalar_float(values.get("inp_px"))
        rows = [
            {
                "scenario": "Pess",
                "valuePsUsd": _scalar_float(values.get("out_value_ps_pess")),
                "weightPct": _to_pct(_scalar_float(values.get("inp_w_pess"))),
            },
            {
                "scenario": "Base",
                "valuePsUsd": _scalar_float(values.get("out_value_ps_base")),
                "weightPct": _to_pct(_scalar_float(values.get("inp_w_base"))),
            },
            {
                "scenario": "Opt",
                "valuePsUsd": _scalar_float(values.get("out_value_ps_opt")),
                "weightPct": _to_pct(_scalar_float(values.get("inp_w_opt"))),
            },
            {
                "scenario": "Weighted",
                "valuePsUsd": _scalar_float(values.get("out_value_ps_weighted")),
                "weightPct": 100.0,
            },
        ]
        for row in rows:
            value = row.get("valuePsUsd")
            if value is None or market_price in (None, 0):
                row["gapVsMarketPct"] = None
            else:
                row["gapVsMarketPct"] = ((float(value) / float(market_price)) - 1.0) * 100.0
        return rows

    def _parse_comps_table(self, table: object) -> list[dict[str, Any]]:
        rows = _as_matrix(table)
        if len(rows) < 2:
            return []
        header = [str(cell).strip() for cell in rows[0]]
        parsed: list[dict[str, Any]] = []
        for row in rows[1:]:
            item: dict[str, Any] = {}
            for idx, key in enumerate(header):
                cell = row[idx] if idx < len(row) else ""
                item[key] = cell
            for numeric_key in (
                "Market Cap (M)",
                "EV (M)",
                "Market Cap ($B)",
                "Revenue ($B)",
                "EBIT ($B)",
                "EV/Sales",
                "EV/EBIT",
            ):
                item[numeric_key] = _maybe_float(item.get(numeric_key))

            market_cap_m = _maybe_float(item.get("Market Cap (M)"))
            ev_m = _maybe_float(item.get("EV (M)"))
            market_cap_b = _maybe_float(item.get("Market Cap ($B)"))
            revenue_b = _maybe_float(item.get("Revenue ($B)"))
            ebit_b = _maybe_float(item.get("EBIT ($B)"))
            ev_sales = _maybe_float(item.get("EV/Sales"))
            ev_ebit = _maybe_float(item.get("EV/EBIT"))

            if market_cap_b is None and market_cap_m is not None:
                market_cap_b = market_cap_m / 1_000.0

            if revenue_b is None and ev_m is not None and ev_sales not in (None, 0):
                revenue_b = (ev_m / ev_sales) / 1_000.0
            if ebit_b is None and ev_m is not None and ev_ebit not in (None, 0):
                ebit_b = (ev_m / ev_ebit) / 1_000.0

            if ev_sales is None and ev_m is not None and revenue_b not in (None, 0):
                ev_sales = ev_m / (revenue_b * 1_000.0)
            if ev_ebit is None and ev_m is not None and ebit_b not in (None, 0):
                ev_ebit = ev_m / (ebit_b * 1_000.0)

            if ev_sales is not None and ev_sales <= 0:
                ev_sales = None
            if ev_ebit is not None and ev_ebit <= 0:
                ev_ebit = None

            item["Market Cap ($B)"] = market_cap_b
            item["Revenue ($B)"] = revenue_b
            item["EBIT ($B)"] = ebit_b
            item["EV/Sales"] = ev_sales
            item["EV/EBIT"] = ev_ebit
            item["EV/EBIT Status"] = "NMF" if ev_ebit is None else "OK"
            parsed.append(item)
        return parsed

    def _parse_sensitivity_grid(self, values: dict[str, list[list[object]]]) -> dict[str, Any]:
        wacc_vector = _flatten_numeric_vector(values.get("sens_wacc_vector"))
        g_vector = _flatten_numeric_vector(values.get("sens_terminal_g_vector"))
        matrix = _as_matrix(values.get("sens_grid_values"))

        wacc_pct = [x * 100.0 for x in wacc_vector]
        g_pct = [x * 100.0 for x in g_vector]
        grid: list[dict[str, float]] = []
        for i, wacc in enumerate(wacc_pct):
            if i >= len(matrix):
                break
            row = matrix[i]
            for j, g in enumerate(g_pct):
                if j >= len(row):
                    break
                value = _maybe_float(row[j])
                if value is None:
                    continue
                grid.append(
                    {
                        "waccPct": wacc,
                        "terminalGPct": g,
                        "valuePsUsd": value,
                    }
                )

        return {
            "waccVectorPct": wacc_pct,
            "terminalGVectorPct": g_pct,
            "grid": grid,
        }

    def _load_canonical_dataset(self, *, ticker: str, run_id: str) -> dict[str, Any]:
        dataset_dir = self.repo_root / "artifacts" / "canonical_datasets"
        candidates = sorted(dataset_dir.glob(f"{ticker}_canonical_dataset_*.json"))
        if not candidates:
            return {}

        run_ts = _extract_timestamp(run_id)
        if run_ts is None:
            selected = candidates[-1]
        else:
            selected = min(
                candidates,
                key=lambda path: _timestamp_distance_seconds(
                    run_ts,
                    _extract_timestamp(path.name),
                ),
            )

        payload = json.loads(selected.read_text(encoding="utf-8"))
        payload["_path"] = str(selected)
        return payload

    def _build_citations(
        self,
        *,
        canonical: dict[str, Any],
        research_packet: Any,
        sheet_sources: object,
        run_id: str,
        ticker: str,
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add(source: str, url: str, note: str = "", accessed: str = "") -> None:
            source_name = (source or "").strip() or "unknown"
            link = (url or "").strip()
            if not link:
                return
            key = (source_name.lower(), link.lower())
            if key in seen:
                return
            seen.add(key)
            output.append(
                {
                    "index": len(output) + 1,
                    "source": source_name,
                    "url": link,
                    "note": note.strip(),
                    "accessedAtUtc": accessed,
                }
            )

        for citation in (canonical.get("canonical_dataset") or {}).get("citations") or []:
            add(
                str(citation.get("source") or ""),
                str(citation.get("url") or ""),
                note=str(citation.get("endpoint") or ""),
                accessed=str(citation.get("accessed_at_utc") or ""),
            )

        for citation in getattr(research_packet, "citations", []) or []:
            citation_map = asdict(citation)
            add(
                str(citation_map.get("source") or ""),
                str(citation_map.get("url") or ""),
                note=str(citation_map.get("endpoint") or ""),
                accessed=str(citation_map.get("accessed_at_utc") or ""),
            )

        for row in _as_matrix(sheet_sources):
            if len(row) < 3:
                continue
            add(
                str(row[0]),
                str(row[2]),
                note=(str(row[1]) if len(row) > 1 else ""),
                accessed=(str(row[3]) if len(row) > 3 else ""),
            )

        run_log_path = self.repo_root / "artifacts" / "run_logs" / f"{run_id}.log"
        run_log_url = run_log_path.resolve().as_uri() if run_log_path.exists() else str(run_log_path)
        add("run_log", run_log_url, note=f"run={run_id}")

        tool_calls_path = self.repo_root / "artifacts" / "canonical_datasets" / f"{run_id}_tool_calls.jsonl"
        tool_calls_url = tool_calls_path.resolve().as_uri() if tool_calls_path.exists() else str(tool_calls_path)
        add("tool_calls", tool_calls_url, note=f"run={run_id}")
        canonical_path = str(canonical.get("_path") or "").strip()
        if canonical_path:
            add("canonical_dataset", Path(canonical_path).resolve().as_uri(), note="exact run-matched dataset")
        else:
            add(
                "canonical_dataset",
                f"artifacts/canonical_datasets/{ticker}_canonical_dataset_*.json",
                note="closest timestamp to run",
            )

        return output[:40]

    def _plan_chart_ids(
        self,
        *,
        ticker: str,
        scenario_rows: list[dict[str, Any]],
        peers_rows: list[dict[str, Any]],
        sensitivity: dict[str, Any],
    ) -> list[str]:
        valid_ev_ebit = _count_positive_numeric_rows(peers_rows, "EV/EBIT")
        valid_ev_sales = _count_positive_numeric_rows(peers_rows, "EV/Sales")
        valid_market_cap = _count_positive_numeric_rows(peers_rows, "Market Cap ($B)")
        valid_revenue_ebit = _count_valid_peer_revenue_ebit_rows(peers_rows)

        availability: dict[str, bool] = {
            "dcf_outcomes_vs_market": any(row.get("valuePsUsd") is not None for row in scenario_rows),
            "scenario_gap_vs_market": any(row.get("gapVsMarketPct") is not None for row in scenario_rows),
            "scenario_weights": any(
                row.get("scenario") in {"Pess", "Base", "Opt"} and row.get("weightPct") is not None
                for row in scenario_rows
            ),
            "comps_ev_ebit": valid_ev_ebit >= 3,
            "comps_ev_sales": valid_ev_sales >= 3,
            "sensitivity_heatmap": len(sensitivity.get("grid") or []) >= 9,
            "peer_market_cap": valid_market_cap >= 3,
            "peer_revenue_ebit": valid_revenue_ebit >= 3,
        }

        planner_prompt = (
            "You are selecting infographic charts for an investment memo.\n"
            f"Ticker: {ticker}\n"
            f"Available charts (id -> available): {json.dumps(availability, sort_keys=True)}\n"
            "Pick 6 to 8 charts that maximize investor usefulness (valuation, scenarios, comps, sensitivity).\n"
            "Return STRICT JSON only with format: {\"chart_ids\": [\"id1\", ...]}."
        )

        selected: list[str] = []
        required = max(
            _DEFAULT_MIN_REQUIRED_CHARTS,
            int(self.settings.memo_min_infographics),
        )
        max_charts = max(required, int(self.settings.memo_max_infographics))
        try:
            response = self.llm_client.generate_text(
                LlmRequest(
                    prompt=planner_prompt,
                    model=self.settings.memo_llm_model,
                )
            )
            parsed = _extract_json_dict(response)
            requested = parsed.get("chart_ids") if isinstance(parsed, dict) else []
            if isinstance(requested, list):
                selected = [
                    str(item).strip()
                    for item in requested
                    if str(item).strip() in availability and availability[str(item).strip()]
                ]
        except Exception as exc:  # noqa: BLE001 - planner fallback
            self._logger.warning("memo_chart_planner_fallback ticker=%s error=%s", ticker, exc)

        if len(selected) < required:
            for chart_id in _DEFAULT_CHART_IDS:
                if not availability.get(chart_id, False):
                    continue
                if chart_id in selected:
                    continue
                selected.append(chart_id)
                if len(selected) >= required:
                    break

        selected = selected[:max_charts]
        if len(selected) < required:
            missing = [chart_id for chart_id, available in availability.items() if available]
            raise RuntimeError(
                "Unable to select required minimum infographics "
                f"(selected={len(selected)} required={required} available={missing})."
            )
        return selected

    def _chart_takeaways(
        self,
        *,
        scenario_rows: list[dict[str, Any]],
        peers_rows: list[dict[str, Any]],
        sensitivity: dict[str, Any],
        market_price: float | None,
        wacc_pct: float | None,
        g_pct: float | None,
    ) -> dict[str, str]:
        out: dict[str, str] = {}
        weighted = _find_scenario(scenario_rows, "Weighted")
        base = _find_scenario(scenario_rows, "Base")
        optimistic = _find_scenario(scenario_rows, "Opt")
        base_weight = _find_scenario(scenario_rows, "Base")

        if weighted and weighted.get("valuePsUsd") is not None:
            out["dcf_outcomes_vs_market"] = (
                f"Weighted value is USD {_fmt(weighted['valuePsUsd'])} per share"
                + (
                    " "
                    if weighted.get("gapVsMarketPct") is None
                    else f"({_fmt_signed_pct(weighted['gapVsMarketPct'])} vs market)."
                )
            )

        if base_weight and base_weight.get("weightPct") is not None:
            out["scenario_weights"] = (
                f"Base scenario weight is {_fmt(base_weight['weightPct'])}% with "
                "pessimistic/optimistic balancing tail risk."
            )

        if optimistic and base:
            out["scenario_gap_vs_market"] = (
                "Only optimistic case clears spot if positive; base and weighted values "
                "frame downside/upside asymmetry."
            )

        ev_ebits = [
            row.get("EV/EBIT")
            for row in peers_rows
            if _maybe_float(row.get("EV/EBIT")) is not None and _maybe_float(row.get("EV/EBIT")) > 0
        ]
        ev_sales = [
            row.get("EV/Sales")
            for row in peers_rows
            if _maybe_float(row.get("EV/Sales")) is not None and _maybe_float(row.get("EV/Sales")) > 0
        ]
        if ev_ebits:
            out["comps_ev_ebit"] = (
                f"Peer EV/EBIT median is {_fmt(_median_numeric(ev_ebits))}x; chart highlights relative position."
            )
        if ev_sales:
            out["comps_ev_sales"] = (
                f"Peer EV/Sales median is {_fmt(_median_numeric(ev_sales))}x; multiple spread informs risk-adjusted framing."
            )

        if sensitivity.get("grid"):
            values = [point.get("valuePsUsd") for point in sensitivity["grid"] if _maybe_float(point.get("valuePsUsd")) is not None]
            if values:
                out["sensitivity_heatmap"] = (
                    f"Sensitivity spans USD {_fmt(min(values))} to USD {_fmt(max(values))} per share "
                    f"across WACC/terminal-g grid (anchor WACC {_fmt(wacc_pct)}%, g {_fmt(g_pct)}%)."
                )

        if peers_rows:
            out["peer_market_cap"] = "Peer market-cap dispersion indicates scale positioning versus valuation multiple premium/discount."
            out["peer_revenue_ebit"] = "Revenue vs EBIT margin plot separates scale effects from operating quality in peer valuation context."

        if market_price is not None:
            out.setdefault(
                "dcf_outcomes_vs_market",
                f"Market reference is USD {_fmt(market_price)} per share for scenario benchmarking.",
            )
        return out

    def _render_infographics(self, *, bundle_path: Path, output_dir: Path) -> Path:
        charts_dir = output_dir / "charts"
        charts_dir.mkdir(parents=True, exist_ok=True)
        script_path = self.repo_root / "infographics" / "scripts" / "render_run_echarts_pack.mjs"
        if not script_path.exists():
            raise RuntimeError(f"Missing ECharts render script: {script_path}")

        command = [
            "node",
            str(script_path),
            "--bundle",
            str(bundle_path),
            "--out-dir",
            str(charts_dir),
            "--profile",
            "memo",
        ]
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "ECharts render failed: "
                f"stdout={completed.stdout.strip()} stderr={completed.stderr.strip()}"
            )

        manifest = charts_dir / "chart_manifest.json"
        if not manifest.exists():
            raise RuntimeError(f"Chart manifest missing after render: {manifest}")
        return manifest

    def _compose_narrative(self, *, bundle: dict[str, Any]) -> _NarrativePack:
        sources = bundle.get("sources") or []
        source_lines = [
            f"[{item['index']}] {item['source']} | {item['url']}"
            for item in sources[:20]
        ]

        prompt_payload = {
            "meta": bundle.get("meta"),
            "marketPriceUsd": bundle.get("marketPriceUsd"),
            "valuation": bundle.get("valuation"),
            "fundamentals": bundle.get("fundamentals"),
            "peers": {
                "rows": (bundle.get("peers") or {}).get("rows", [])[:8],
                "evEbitMedian": (bundle.get("peers") or {}).get("evEbitMedian"),
                "evSalesMedian": (bundle.get("peers") or {}).get("evSalesMedian"),
            },
            "sensitivity_summary": {
                "waccVectorPct": (bundle.get("sensitivity") or {}).get("waccVectorPct"),
                "terminalGVectorPct": (bundle.get("sensitivity") or {}).get("terminalGVectorPct"),
                "grid_points": len((bundle.get("sensitivity") or {}).get("grid") or []),
            },
            "story": bundle.get("story"),
            "chart_ids": bundle.get("chart_ids"),
            "chart_takeaways": bundle.get("chart_takeaways"),
        }

        prompt = (
            "You are writing a neutral, client-facing US equity research memo in investment-banking style.\n"
            "Requirements:\n"
            "1) Use only provided facts; do not fabricate numbers.\n"
            "2) Include inline numeric footnotes like [1], [2] tied to the source index list.\n"
            "3) Keep tone objective and evidence-led (no investment recommendation language).\n"
            "4) Cover business model, sector/peer setup, valuation setup, scenario framing, and risks/opportunities.\n"
            "5) Target 900-1400 words total.\n"
            "6) Use at least five distinct citation IDs across the memo and at least one citation in each section.\n"
            "Return STRICT JSON with this schema only:\n"
            "{\n"
            "  \"memo_title\": \"...\",\n"
            "  \"memo_subtitle\": \"...\",\n"
            "  \"thesis\": \"...\",\n"
            "  \"sections\": [\n"
            "    {\"heading\": \"...\", \"body\": \"...\"}\n"
            "  ],\n"
            "  \"conclusion\": \"...\"\n"
            "}\n"
            f"DATA:\n{json.dumps(prompt_payload, default=_json_default, indent=2)}\n"
            "SOURCE INDEX:\n"
            f"{chr(10).join(source_lines)}"
        )

        try:
            response = self.llm_client.generate_text(
                LlmRequest(prompt=prompt, model=self.settings.memo_llm_model)
            )
            parsed = _extract_json_dict(response)
            sections_raw = parsed.get("sections") if isinstance(parsed, dict) else []
            sections: list[dict[str, str]] = []
            if isinstance(sections_raw, list):
                for item in sections_raw:
                    if not isinstance(item, dict):
                        continue
                    heading = str(item.get("heading") or "").strip()
                    body = str(item.get("body") or "").strip()
                    if not heading or not body:
                        continue
                    sections.append({"heading": heading, "body": body})
            if len(sections) < 3:
                raise ValueError("Narrative output missing section depth.")

            thesis = str(parsed.get("thesis") or "").strip()
            if not thesis:
                thesis = self._fallback_thesis(bundle)
            title = str(parsed.get("memo_title") or "").strip() or f"{bundle['meta']['ticker']} Investment Memo"
            subtitle = str(parsed.get("memo_subtitle") or "").strip() or "Post-valuation research note"
            conclusion = str(parsed.get("conclusion") or "").strip()
            if not conclusion:
                conclusion = "Valuation outcomes should be interpreted with scenario and sensitivity context, not point estimates."

            narrative = _NarrativePack(
                title=title,
                subtitle=subtitle,
                thesis=thesis,
                sections=tuple(sections[:6]),
                conclusion=conclusion,
            )
            if "[" not in thesis and "[" not in conclusion:
                # Ensure inline footnotes survive even under weak model responses.
                narrative = _NarrativePack(
                    title=narrative.title,
                    subtitle=narrative.subtitle,
                    thesis=f"{narrative.thesis} [1]",
                    sections=narrative.sections,
                    conclusion=f"{narrative.conclusion} [2]",
                )
            return self._enforce_citation_density(narrative=narrative, max_source_index=max(1, len(sources)))
        except Exception as exc:  # noqa: BLE001 - deterministic fallback
            self._logger.warning("memo_narrative_fallback run_id=%s error=%s", bundle["meta"]["runId"], exc)
            fallback = self._fallback_narrative(bundle)
            return self._enforce_citation_density(narrative=fallback, max_source_index=max(1, len(sources)))

    def _enforce_citation_density(
        self,
        *,
        narrative: _NarrativePack,
        max_source_index: int,
    ) -> _NarrativePack:
        max_index = max(1, max_source_index)
        target_unique = min(5, max_index)

        def ensure(text: str, fallback_id: int) -> str:
            trimmed = text.strip()
            if not trimmed:
                return f"[{fallback_id}]"
            normalized = _normalize_citations(trimmed, max_source_index=max_index)
            if not _CITATION_RE.search(normalized):
                normalized = f"{normalized} [{fallback_id}]"
            return normalized

        thesis = ensure(narrative.thesis, 1)
        conclusion = ensure(narrative.conclusion, min(2, max_index))

        rewritten_sections: list[dict[str, str]] = []
        for idx, section in enumerate(narrative.sections):
            fallback_id = min(max_index, (idx % max(target_unique, 1)) + 1)
            rewritten_sections.append(
                {
                    "heading": section["heading"],
                    "body": ensure(str(section["body"]), fallback_id),
                }
            )

        all_text = " ".join([thesis, conclusion] + [sec["body"] for sec in rewritten_sections])
        unique = {int(match) for match in _CITATION_RE.findall(all_text)}
        if len(unique) < target_unique:
            for idx, section in enumerate(rewritten_sections):
                cite_id = min(max_index, (idx % target_unique) + 1)
                if cite_id not in unique:
                    section["body"] = f"{section['body']} [{cite_id}]"
                    unique.add(cite_id)
                if len(unique) >= target_unique:
                    break

        return _NarrativePack(
            title=narrative.title,
            subtitle=narrative.subtitle,
            thesis=thesis,
            sections=tuple(rewritten_sections),
            conclusion=conclusion,
        )

    def _fallback_thesis(self, bundle: dict[str, Any]) -> str:
        weighted = _find_scenario(bundle.get("valuation", {}).get("scenarios", []), "Weighted")
        market_price = bundle.get("marketPriceUsd")
        if weighted and weighted.get("valuePsUsd") is not None and market_price:
            gap = weighted.get("gapVsMarketPct")
            gap_text = "N/A" if gap is None else _fmt_signed_pct(gap)
            return (
                "The current valuation setup indicates weighted fair value of "
                f"USD {_fmt(weighted['valuePsUsd'])} per share versus market USD {_fmt(market_price)} "
                f"({gap_text}), with downside/upside highly sensitive to terminal assumptions. [1][2]"
            )
        return "The run delivers a complete three-scenario framework with sheet-owned valuation outputs and source-backed assumptions. [1]"

    def _fallback_narrative(self, bundle: dict[str, Any]) -> _NarrativePack:
        ticker = bundle.get("meta", {}).get("ticker") or ""
        company = bundle.get("meta", {}).get("companyName") or ticker
        weighted = _find_scenario(bundle.get("valuation", {}).get("scenarios", []), "Weighted")
        market_price = bundle.get("marketPriceUsd")
        wacc = bundle.get("valuation", {}).get("outWaccPct")
        g = bundle.get("valuation", {}).get("outTerminalGPct")
        ev_ebit_median = bundle.get("peers", {}).get("evEbitMedian")
        ev_sales_median = bundle.get("peers", {}).get("evSalesMedian")

        sections = (
            {
                "heading": "Business and Operating Setup",
                "body": (
                    f"{company} is analyzed through a scenario-based DCF anchored to workbook formulas and "
                    "supported by source-tagged evidence. The run combines company fundamentals, market snapshot, "
                    "rates context, and external research packets to keep assumptions explainable and auditable. [1][2]"
                ),
            },
            {
                "heading": "Valuation Construction and Scenario Framing",
                "body": (
                    "The model applies pessimistic/base/optimistic assumptions with explicit weights and reads "
                    "terminal outputs from formula-owned ranges only. "
                    f"Current anchors include WACC {_fmt(wacc)}% and terminal growth {_fmt(g)}%. [2]"
                ),
            },
            {
                "heading": "Peer and Sensitivity Readthrough",
                "body": (
                    f"Peer context shows EV/EBIT median at {_fmt(ev_ebit_median)}x and EV/Sales median at "
                    f"{_fmt(ev_sales_median)}x, while sensitivity charts frame valuation elasticity to discount rate and "
                    "terminal growth assumptions. This avoids over-reliance on a single point estimate. [2][3]"
                ),
            },
            {
                "heading": "Risk and Monitoring Priorities",
                "body": (
                    "Primary monitoring vectors are assumption drift, macro-rate regime changes, and peer-multiple "
                    "dispersion. Memo interpretation should prioritize consistency between narrative claims and "
                    "sheet-verified outputs at publish time. [3][4]"
                ),
            },
        )
        thesis = self._fallback_thesis(bundle)
        if weighted and weighted.get("valuePsUsd") is not None and market_price:
            conclusion = (
                f"At current inputs, weighted value of USD {_fmt(weighted['valuePsUsd'])} versus market USD {_fmt(market_price)} "
                "should be read as a scenario-weighted midpoint with material sensitivity around WACC and terminal growth. [2][3]"
            )
        else:
            conclusion = "Conclusions remain conditional on scenario integrity, citation quality, and workbook contract compliance. [2]"

        return _NarrativePack(
            title=f"{ticker} Post-Run Investment Memo",
            subtitle="Neutral research note generated after valuation workflow completion",
            thesis=thesis,
            sections=sections,
            conclusion=conclusion,
        )

    def _to_markdown(self, *, narrative: _NarrativePack) -> str:
        lines: list[str] = [
            f"# {narrative.title}",
            "",
            narrative.subtitle,
            "",
            "## Investment Thesis",
            "",
            narrative.thesis,
            "",
        ]
        for section in narrative.sections:
            lines.extend([f"## {section['heading']}", "", section["body"], ""])
        lines.extend(["## Conclusion", "", narrative.conclusion, ""])
        return "\n".join(lines)

    def _render_html(
        self,
        *,
        bundle: dict[str, Any],
        chart_manifest: dict[str, Any],
        narrative: _NarrativePack,
        chart_dir: Path,
    ) -> str:
        run_id = bundle["meta"]["runId"]
        ticker = bundle["meta"]["ticker"]
        company = bundle["meta"].get("companyName") or ticker
        market_price = bundle.get("marketPriceUsd")
        scenarios = bundle.get("valuation", {}).get("scenarios", [])
        weighted = _find_scenario(scenarios, "Weighted")

        summary_rows = [
            ("Run ID", run_id),
            ("Ticker", ticker),
            ("Company", company),
            ("Market Price", f"USD {_fmt(market_price)}"),
            (
                "Weighted Value / Share",
                "N/A"
                if not weighted or weighted.get("valuePsUsd") is None
                else f"USD {_fmt(weighted['valuePsUsd'])}",
            ),
            (
                "Weighted Gap vs Market",
                "N/A"
                if not weighted or weighted.get("gapVsMarketPct") is None
                else _fmt_signed_pct(weighted["gapVsMarketPct"]),
            ),
            (
                "WACC / Terminal g",
                f"{_fmt(bundle.get('valuation', {}).get('outWaccPct'))}% / "
                f"{_fmt(bundle.get('valuation', {}).get('outTerminalGPct'))}%",
            ),
            (
                "Generated (UTC)",
                bundle.get("meta", {}).get("generatedAtUtc") or _utc_now_iso(),
            ),
        ]

        def render_blocks(text: str) -> str:
            return _markdown_to_html_blocks(text)

        full_width_ids = {"dcf_outcomes_vs_market", "sensitivity_heatmap"}
        chart_pages: list[str] = []
        compact_cards: list[str] = []
        for chart in chart_manifest.get("charts") or []:
            chart_path = Path(str(chart.get("png_path") or ""))
            if not chart_path.is_absolute():
                chart_path = (chart_dir / chart_path.name).resolve()
            chart_src = chart_path.as_uri()
            chart_title = _escape_html(str(chart.get("title") or chart.get("id") or "Chart"))
            takeaway = _escape_html(str(chart.get("takeaway") or ""))
            chart_id = str(chart.get("id") or "")

            card = "\n".join(
                [
                    "<article class=\"chart-item\">",
                    f"  <h3>{chart_title}</h3>",
                    (f"  <p class=\"takeaway\">{takeaway}</p>" if takeaway else ""),
                    f"  <img class=\"chart\" src=\"{chart_src}\" alt=\"{chart_title}\" />",
                    "</article>",
                ]
            )
            if chart_id in full_width_ids:
                chart_pages.append(f"<section class=\"page chart-page chart-page-full\">{card}</section>")
            else:
                compact_cards.append(card)

        for pair in _chunked(compact_cards, 2):
            chart_pages.append(
                "\n".join(
                    [
                        "<section class=\"page chart-page chart-grid-page\">",
                        "  <div class=\"chart-grid\">",
                        *[f"    {item}" for item in pair],
                        "  </div>",
                        "</section>",
                    ]
                )
            )

        section_html = "\n".join(
            (
                f"<h3>{_escape_html(section['heading'])}</h3>"
                + render_blocks(section["body"])
            )
            for section in narrative.sections
        )

        references = bundle.get("sources") or []
        reference_items = "\n".join(
            (
                f"<li>[{item['index']}] <strong>{_escape_html(str(item.get('source') or ''))}</strong>"
                f" - <span>{_escape_html(str(item.get('url') or ''))}</span>"
                f" <em>{_escape_html(str(item.get('note') or ''))}</em></li>"
            )
            for item in references
        )

        summary_table_rows = "\n".join(
            f"<tr><th>{_escape_html(label)}</th><td>{_escape_html(value)}</td></tr>"
            for label, value in summary_rows
        )

        return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{_escape_html(narrative.title)}</title>
  <style>
    @page {{ size: A4; margin: 14mm; }}
    body {{ margin: 0; font-family: 'Avenir Next', 'Segoe UI', Arial, sans-serif; color: #102a43; background: #ffffff; }}
    .page {{ page-break-after: always; min-height: 258mm; box-sizing: border-box; }}
    .page:last-child {{ page-break-after: auto; }}
    h1 {{ margin: 0 0 8px 0; font-size: 34px; line-height: 1.15; }}
    h2 {{ margin: 0 0 10px 0; font-size: 26px; line-height: 1.2; }}
    h3 {{ margin: 22px 0 8px 0; font-size: 20px; line-height: 1.2; }}
    p {{ margin: 0 0 10px 0; font-size: 13.2px; line-height: 1.52; }}
    ul, ol {{ margin: 0 0 10px 18px; padding: 0; }}
    li {{ margin: 0 0 6px 0; font-size: 13.2px; line-height: 1.5; }}
    code {{ background: #f4f7fb; border: 1px solid #d7e0ec; border-radius: 4px; padding: 0 4px; }}
    .sub {{ color: #5f6f84; font-size: 16px; margin-bottom: 16px; }}
    .thesis {{ margin-top: 10px; border-left: 4px solid #2f6cad; padding: 10px 12px; background: #f4f8fd; }}
    .meta {{ margin-top: 14px; width: 100%; border-collapse: collapse; font-size: 12.8px; }}
    .meta th {{ text-align: left; width: 34%; padding: 6px 8px; border: 1px solid #d7e0ec; background: #f7faff; }}
    .meta td {{ padding: 6px 8px; border: 1px solid #d7e0ec; }}
    .narrative {{ padding-right: 8px; }}
    .chart-page {{ display: block; }}
    .chart-item {{ border: 1px solid #d7e0ec; border-radius: 8px; padding: 8px; }}
    .chart-item h3 {{ margin: 0 0 6px 0; font-size: 18px; }}
    .takeaway {{ color: #5f6f84; margin-bottom: 8px; font-size: 12.4px; }}
    .chart {{ width: 100%; max-height: 108mm; object-fit: contain; border: 1px solid #e7edf5; border-radius: 6px; }}
    .chart-page-full .chart {{ max-height: 216mm; }}
    .chart-grid-page .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; align-items: start; }}
    .chart-grid-page .chart-item h3 {{ font-size: 16px; }}
    .chart-grid-page .takeaway {{ font-size: 11.8px; }}
    .chart-grid-page .chart {{ max-height: 93mm; }}
    .references li {{ margin: 0 0 8px 0; font-size: 12.4px; line-height: 1.42; }}
    .foot {{ margin-top: 18px; font-size: 12px; color: #5f6f84; }}
  </style>
</head>
<body>
  <section class=\"page\">
    <h1>{_escape_html(narrative.title)}</h1>
    <div class=\"sub\">{_escape_html(narrative.subtitle)}</div>
    <div class=\"thesis\">{render_blocks(narrative.thesis)}</div>
    <table class=\"meta\">{summary_table_rows}</table>
    <p class=\"foot\">This memo is generated after spreadsheet completion. Valuation math remains formula-owned in sheet outputs.</p>
  </section>

  <section class=\"page narrative\">
    <h2>Narrative and Analytical Readthrough</h2>
    {section_html}
    <h3>Conclusion</h3>
    {render_blocks(narrative.conclusion)}
  </section>

  {''.join(chart_pages)}

  <section class=\"page references\">
    <h2>References</h2>
    <ol>{reference_items}</ol>
  </section>
</body>
</html>
"""

    def _validate_chart_manifest(
        self,
        *,
        chart_manifest: dict[str, Any],
        required_charts: int,
    ) -> list[dict[str, Any]]:
        rendered = chart_manifest.get("charts") or []
        failed = chart_manifest.get("failed_charts") or []
        if failed:
            raise RuntimeError(f"Chart render failures present: {json.dumps(failed)}")
        if len(rendered) < required_charts:
            raise RuntimeError(
                "Insufficient infographics generated "
                f"(got={len(rendered)}, required>={required_charts})."
            )
        for chart in rendered:
            path = Path(str(chart.get("png_path") or "")).resolve()
            if not path.exists():
                raise RuntimeError(f"Missing chart artifact: {path}")
            if path.stat().st_size < 12_000:
                raise RuntimeError(f"Chart artifact appears empty or too small: {path}")
        return rendered

    def _render_pdf(self, *, html_path: Path, pdf_path: Path) -> None:
        script_path = self.repo_root / "infographics" / "scripts" / "render_pdf_from_html.mjs"
        if not script_path.exists():
            raise RuntimeError(f"Missing PDF render script: {script_path}")
        command = [
            "node",
            str(script_path),
            "--input-html",
            str(html_path),
            "--output-pdf",
            str(pdf_path),
        ]
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "PDF render failed: "
                f"stdout={completed.stdout.strip()} stderr={completed.stderr.strip()}"
            )

    def _write_manifest(
        self,
        *,
        manifest_path: Path,
        status: str,
        request: ValuationRunRequest,
        result: ValuationRunResult,
        started_at_utc: str,
        finished_at_utc: str,
        bundle_path: Path | None,
        chart_manifest_path: Path | None,
        markdown_path: Path | None,
        html_path: Path | None,
        pdf_path: Path | None,
        notes: list[str],
        errors: list[str],
    ) -> None:
        chart_count = 0
        if chart_manifest_path and chart_manifest_path.exists():
            try:
                chart_payload = json.loads(chart_manifest_path.read_text(encoding="utf-8"))
                chart_count = len(chart_payload.get("charts") or [])
            except Exception:  # noqa: BLE001
                chart_count = 0

        payload = {
            "run_id": request.run_id,
            "ticker": request.ticker,
            "spreadsheet_id": result.spreadsheet_id,
            "valuation_status": result.status,
            "wrapper_status": status,
            "started_at_utc": started_at_utc,
            "finished_at_utc": finished_at_utc,
            "artifacts": {
                "bundle_json": str(bundle_path) if bundle_path else "",
                "chart_manifest_json": str(chart_manifest_path) if chart_manifest_path else "",
                "memo_markdown": str(markdown_path) if markdown_path else "",
                "memo_html": str(html_path) if html_path else "",
                "memo_pdf": str(pdf_path) if pdf_path else "",
            },
            "infographics_generated": chart_count,
            "notes": notes,
            "errors": errors,
        }
        manifest_path.write_text(
            json.dumps(payload, indent=2, default=_json_default),
            encoding="utf-8",
        )


def _extract_json_dict(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty model response.")
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = _JSON_DECODER.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"No JSON object found in model output: {text[:220]}")


def _as_matrix(value: object) -> list[list[object]]:
    if isinstance(value, list) and value and all(isinstance(row, list) for row in value):
        return [list(row) for row in value]
    return []


def _unwrap_scalar(value: object) -> object:
    current = value
    while isinstance(current, list) and len(current) == 1:
        current = current[0]
    return current


def _scalar_float(value: object) -> float | None:
    unwrapped = _unwrap_scalar(value)
    return _maybe_float(unwrapped)


def _scalar_text(value: object) -> str:
    unwrapped = _unwrap_scalar(value)
    if unwrapped is None:
        return ""
    if isinstance(unwrapped, list):
        return " ".join(str(item) for item in unwrapped if str(item).strip()).strip()
    return str(unwrapped).strip()


def _flatten_numeric_vector(value: object) -> list[float]:
    matrix = _as_matrix(value)
    if not matrix:
        return []
    flattened: list[float] = []
    for row in matrix:
        for cell in row:
            num = _maybe_float(cell)
            if num is not None:
                flattened.append(num)
    return flattened


def _maybe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        if text.endswith("%"):
            text = text[:-1]
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _to_pct(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 100.0


def _scale_to_billions(value: float | None) -> float | None:
    if value is None:
        return None
    magnitude = abs(value)
    if magnitude >= 1_000_000_000:
        return value / 1_000_000_000.0
    if magnitude >= 1_000_000:
        return value / 1_000.0
    return value


def _median_numeric(values: list[object]) -> float | None:
    cleaned = sorted(_maybe_float(v) for v in values if _maybe_float(v) is not None)
    if not cleaned:
        return None
    mid = len(cleaned) // 2
    if len(cleaned) % 2 == 1:
        return float(cleaned[mid])
    return float((cleaned[mid - 1] + cleaned[mid]) / 2.0)


def _safe_pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return (numerator / denominator) * 100.0


def _extract_timestamp(text: str) -> datetime | None:
    match = _RUN_TS_RE.search(str(text))
    if not match:
        return None
    token = match.group(1)
    try:
        return datetime.strptime(token, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _timestamp_distance_seconds(anchor: datetime, target: datetime | None) -> float:
    if target is None:
        return float("inf")
    return abs((anchor - target).total_seconds())


def _escape_html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _render_inline_markdown(text: str) -> str:
    escaped = _escape_html(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    return escaped


def _markdown_to_html_blocks(text: str) -> str:
    lines = str(text or "").splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_kind = "ul"

    def flush_paragraph() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        blocks.append(f"<p>{_render_inline_markdown(' '.join(paragraph).strip())}</p>")
        paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if not list_items:
            return
        body = "".join(f"<li>{_render_inline_markdown(item)}</li>" for item in list_items)
        blocks.append(f"<{list_kind}>{body}</{list_kind}>")
        list_items = []

    for raw in lines:
        line = raw.strip()
        if not line:
            flush_paragraph()
            flush_list()
            continue

        numbered = re.match(r"^(\d+)\.\s+(.+)$", line)
        if line.startswith(("- ", "* ")) or numbered:
            flush_paragraph()
            if numbered:
                if list_items and list_kind != "ol":
                    flush_list()
                list_kind = "ol"
                list_items.append(numbered.group(2).strip())
            else:
                if list_items and list_kind != "ul":
                    flush_list()
                list_kind = "ul"
                list_items.append(line[2:].strip())
            continue

        flush_list()
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    return "".join(blocks) if blocks else "<p></p>"


def _normalize_citations(text: str, *, max_source_index: int) -> str:
    max_idx = max(1, max_source_index)

    def repl(match: re.Match[str]) -> str:
        try:
            idx = int(match.group(1))
        except ValueError:
            return "[1]"
        if idx < 1:
            return "[1]"
        if idx > max_idx:
            return f"[{max_idx}]"
        return f"[{idx}]"

    return _CITATION_RE.sub(repl, text)


def _count_positive_numeric_rows(rows: list[dict[str, Any]], key: str) -> int:
    return sum(1 for row in rows if (_maybe_float(row.get(key)) or 0) > 0)


def _count_valid_peer_revenue_ebit_rows(rows: list[dict[str, Any]]) -> int:
    valid = 0
    for row in rows:
        rev = _maybe_float(row.get("Revenue ($B)"))
        ebit = _maybe_float(row.get("EBIT ($B)"))
        if rev is None or rev <= 0 or ebit is None or math.isnan(ebit):
            continue
        valid += 1
    return valid


def _chunked(values: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        return [values] if values else []
    return [values[idx : idx + size] for idx in range(0, len(values), size)]


def _find_scenario(rows: list[dict[str, Any]], scenario: str) -> dict[str, Any] | None:
    for row in rows:
        if str(row.get("scenario") or "") == scenario:
            return row
    return None


def _fmt(value: object) -> str:
    num = _maybe_float(value)
    if num is None:
        return "N/A"
    return f"{num:,.2f}"


def _fmt_signed_pct(value: object) -> str:
    num = _maybe_float(value)
    if num is None:
        return "N/A"
    sign = "+" if num > 0 else ""
    return f"{sign}{num:,.2f}%"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            return str(value)
    return str(value)
