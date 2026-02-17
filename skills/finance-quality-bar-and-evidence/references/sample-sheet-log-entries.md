# Sample Sheet Log Entries (High-Quality)

Use these as formatting and content quality examples for `Agent Log` tab entries.

## 1) Action Ledger sample rows

| step | ts_utc | phase | action | tool | target | summary | citations |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-02-15T18:05:12Z | intake | WRITE | google_sheets | `log_run_id`, `inp_ticker` | Initialized run metadata and ticker context. | run_meta |
| 2 | 2026-02-15T18:06:20Z | data | FETCH | sec_edgar_xbrl | `Inputs` staging ranges | Pulled latest 10-K/10-Q facts for revenue, EBIT, tax, shares. | SEC:0000320193-25-000073 |
| 3 | 2026-02-15T18:07:04Z | data | FETCH | finnhub_fundamentals | `inp_px`, `inp_cash`, `inp_debt` | Retrieved market snapshot and capital structure fields; normalized units to USD millions. | finnhub:/quote,/stock/profile2 |
| 4 | 2026-02-15T18:08:02Z | data | FETCH | fred_treasury | `inp_rf`, rates context block | Wrote DGS10 latest close and documented macro regime summary. | FRED:DGS10@2026-02-14 |
| 5 | 2026-02-15T18:09:35Z | data | VALIDATE | source_contradiction_checker | `Checks` contradiction section | Shares outstanding discrepancy 1.2% (below threshold); SEC retained as primary. | SEC vs Finnhub |
| 6 | 2026-02-15T18:11:22Z | assumptions | WRITE | google_sheets | `inp_pess_*`, `inp_base_*`, `inp_opt_*`, `inp_w_*` | Scenario vectors written with sector-adjusted assumptions and explicit confidence labels. | [S1],[S2],[S3],[S4] |
| 7 | 2026-02-15T18:12:41Z | model | READ | google_sheets | `out_value_ps_*`, `out_value_ps_weighted` | Read formula-calculated outputs; no off-sheet arithmetic performed. | sheet:Output |
| 8 | 2026-02-15T18:13:18Z | checks | VALIDATE | google_sheets | `Checks` | Passed `WACC > g`, weights sum, and weighted-formula linkage checks. | sheet:Checks |
| 9 | 2026-02-15T18:14:07Z | memo | WRITE | llm | memo artifact | Drafted memo with all headline numbers mapped to `out_*` ranges. | [S1]-[S6] |
| 10 | 2026-02-15T18:15:02Z | publish | WRITE | google_sheets | `log_status`, `log_end_ts` | Marked run complete and appended summary row to central logbook. | run_closeout |

## 2) Assumption Journal sample rows

| assumption_key | scenario | value_unit | model_location | source | method | rationale | confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| revenue_growth_y1 | pessimistic | 4.0% | `inp_pess_g1` | SEC + transcript | cycle_downside_case | Inventory correction extends longer than base case; downside demand elasticity elevated. | medium |
| revenue_growth_y1 | base | 9.0% | `inp_base_g1` | SEC + transcript + peers | weighted_evidence | Mix and backlog imply moderate normalization with no demand cliff. | medium_high |
| revenue_growth_y1 | optimistic | 14.0% | `inp_opt_g1` | transcript + peer momentum | upside_case | Sustained AI/HPC demand supports above-trend shipments. | low_medium |
| terminal_growth | base | 2.5% | `inp_base_gt` | FRED + long-run GDP proxy | macro_anchor | Set below risk-free anchor and consistent with mature-cycle nominal growth. | high |
| wacc | base | 8.8% | `inp_base_wacc` | FRED + ERP + beta triangulation | bottom_up_wacc | Reflects current rate regime and cyclicality versus peer beta range. | medium_high |
| scenario_weight_base | base | 50% | `inp_w_base` | judgment + sensitivity | probability_weighting | Base remains modal scenario after stress tests; tail risks still meaningful. | medium |

## 3) Story Journal sample rows

| scenario | story_claim | linked_metric | supporting_evidence | risk_to_claim |
| --- | --- | --- | --- | --- |
| pessimistic | Inventory correction lasts through next fiscal year. | `inp_pess_g1..g2` | Management cautionary tone in recent transcript and peer shipment commentary. | Faster normalization would invalidate downside duration assumption. |
| base | Product mix upgrade sustains margin above prior-cycle median. | `inp_base_m5`, `inp_base_m10` | Gross margin bridge in filing plus mix commentary in earnings call. | Competitive pricing pressure can erode margin durability. |
| optimistic | AI/HPC demand extends utilization and operating leverage. | `inp_opt_g1..g3`, `inp_opt_m5` | Order visibility and capacity commentary from management and suppliers. | Demand pull-forward and capex digestion risk can reverse utilization gains. |

## 4) Log quality checklist

1. Every `WRITE` and `READ` call names target ranges or tabs.
2. Every material assumption has source + rationale + confidence.
3. Contradictions are logged with chosen source and reason.
4. Final memo numbers map to `out_*` ranges only.
