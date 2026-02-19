# Phase V1 Implementation Plan

## Goal
Build a high-quality, investment-banking-style, multi-turn finance research agent that starts from a semi pre-populated Google Sheets template, runs a 3-scenario DCF (pessimistic, neutral, optimistic), assigns scenario weights, logs rationale in-sheet, and produces both:
- a high-quality Google Sheets valuation workbook
- a high-quality investment memo

## Architecture diagram (Excalidraw only)
- https://excalidraw.com/#json=WAIZC38Cvi9so_RQ1GAg6,bIAI3iWtgKKj9m56aj1-Gw

## Core constraints
- Template-first run initialization (copy template per run).
- Final valuation outputs must be produced by Google Sheets formulas in the copied run workbook.
- Agent must not compute final enterprise/equity/value-per-share outputs off-sheet.
- Intermediate analytics math is allowed in deterministic Python functions (for example, peer multiple computation and ranking), then written as tabular inputs/evidence into Sheets.
- Assumptions, story, valuation rationale, and citations must be logged in-sheet.
- Agent should ask for missing high-impact data when needed.
- Numeric claims in memo must map to sheet output ranges.
- Post-run formatting pass is deterministic and orchestration-owned (not LLM-owned): auto-resize rows/columns only for `Comps`, `Sources`, `Story`, and `Agent Log`; keep model tabs (`Inputs`, `DCF`, `Sensitivity`, `Checks`, `Output`, `Dilution (TSM)`, `R&D Capitalization`, `Lease Capitalization`) fixed to avoid layout drift.

## Post-run sheet auto-resize policy (implemented)
1. Execution point:
- Run once in `finalize` after final sheet writes (`log_status`, `log_end_ts`) and before run completion.

2. Scope:
- Resize only these presentation/data-heavy tabs: `Comps`, `Sources`, `Story`, `Agent Log`.
- Do not resize core model tabs to preserve IB-style layout stability and formula readability.

3. Implementation contract:
- Per run sheet, orchestration calls Google Sheets `spreadsheets.batchUpdate` with `autoResizeDimensions` requests for both `COLUMNS` and `ROWS` across each targeted tab.
- This is a deterministic, non-LLM step.
- Failures are logged and appended to run notes; they do not alter valuation math or overwrite model assumptions.

## Approved financial-modeling execution order (skill contract)
The financial-modeling skill must execute in this order for each run:
1. `R&D Capitalization` normalization.
2. `Lease Capitalization` normalization.
3. `DCF` scenario setup/execution (pess/base/opt + weights).
4. `Comps` build using industry-specific peer set logic.
5. `Sensitivity` analysis over key drivers.
6. Integrity gate checks (hard-stop on formula/address/data-quality failures).
7. `Story` synthesis and memo linkage as the final step only.

Execution notes:
- Story drafting is deferred until quant outputs are stable.
- Comps must be industry-specific and may use canonical dataset fields and/or fresh tool retrieval for company + peers.
- Python math execution is allowed for intermediate comps/screening calculations, but final valuation outputs remain sheet-calculated.

## Authoritative workbook contract
- Authoritative artifact template: `Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx`.
- The agent must execute valuation work by copying this template and editing only the copied run artifact.
- The final delivered artifact must preserve this workbook structure (tabs + named ranges) and contain fully populated outputs, logs, and memo-grounding references.

Workbook tabs (must be used explicitly by skills):
- `README`: run instructions and operator notes.
- `Inputs`: base and scenario assumptions, weights, core market/valuation inputs.
- `Dilution (TSM)`: treasury stock method dilution mechanics.
- `R&D Capitalization`: R&D normalization adjustments.
- `Lease Capitalization`: lease normalization and debt adjustments.
- `DCF`: forecast and PV engine (formula-driven).
- `Sensitivity`: valuation sensitivity tables/charts.
- `Comps`: peer and relative valuation support.
- `Checks`: model integrity checks and invariant flags.
- `Sources`: citation/provenance register.
- `Story`: narrative, thesis, and what-must-be-true structure.
- `Output`: final valuation outputs and scenario summary.
- `Agent Log`: action ledger, assumption journal, and story journal.

Critical named ranges (must be first-class interfaces):
- Run/meta: `log_run_id`, `log_status`, `log_start_ts`, `log_end_ts`.
- Base assumptions: `inp_base_g1`..`inp_base_g5`, `inp_base_m5`, `inp_base_m10`, `inp_base_tax`, `inp_base_wacc`, `inp_base_gt`.
- Scenario assumptions: `inp_pess_*`, `inp_opt_*`.
- Scenario weights: `inp_w_pess`, `inp_w_base`, `inp_w_opt`.
- Key cost-of-capital drivers: `inp_rf`, `inp_erp`, `inp_beta`, `calc_ke`, `calc_wacc`.
- Capital structure/bridge: `inp_cash`, `inp_debt`, `calc_lease_debt`, `inp_basic_shares`, `calc_diluted_shares`.
- TSM contract: `inp_tsm_tranche1_count_mm`, `inp_tsm_tranche1_strike`, `inp_tsm_tranche1_type`, `inp_tsm_tranche1_note`, `out_tsm_incremental_shares`, `out_tsm_diluted_shares`, `tsm_tranche_table`.
- Sensitivity contract: `sens_base_value_ps`, `sens_wacc_vector`, `sens_terminal_g_vector`, `sens_grid_values`, `sens_grid_full`.
- Comps contract (dynamic, industry-driven): `comps_target_rev_ttm`, `comps_target_ebit_ttm`, `comps_header`, `comps_firstrow`, `comps_table`, `comps_peer_tickers`, `comps_peer_names`, `comps_multiples_header`, `comps_multiples_values`, `comps_table_full`, `comps_method_note`, `comps_peer_count`, `comps_multiple_count`.
- Comps legacy compatibility aliases (until migration complete): `comps_ev_ebit`, `comps_ev_sales`, `comps_pe`, `comps_notes`.
- Story contract: `story_thesis`, `story_growth`, `story_profitability`, `story_reinvestment`, `story_risk`, `story_sanity_checks`, `story_grid_header`, `story_grid_rows`, `story_core_narrative_rows`, `story_linked_operating_driver_rows`, `story_kpi_to_track_rows`, `story_grid_citations`, `story_memo_hooks`.
- Output contract: `out_value_ps_pess`, `out_value_ps_base`, `out_value_ps_opt`, `out_value_ps_weighted`, `out_equity_value_weighted`, `out_enterprise_value_weighted`, `out_wacc`, `out_terminal_g`.
- Logbook anchors: `log_actions_firstrow`, `log_assumptions_firstrow`, `log_story_firstrow`.

## Complete template named-range inventory (authoritative)
- Source workbook: `Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx`
- Count: `158 named ranges` (current snapshot before dynamic-comps/table-anchor extension).
<!-- TEMPLATE_NAMED_RANGES_START -->
- `_xlnm._FilterDatabase` => `'Agent Log'!$B$16:$J$216`
- `calc_diluted_shares` => `'Inputs'!C55`
- `calc_ke` => `'Inputs'!C40`
- `calc_lease_debt` => `'Inputs'!C51`
- `calc_wacc` => `'Inputs'!C43`
- `comps_ev_ebit` => `'Comps'!$D$8:$D$40`
- `comps_ev_sales` => `'Comps'!$E$8:$E$40`
- `comps_header` => `'Comps'!$B$7:$G$7`
- `comps_notes` => `'Comps'!$G$8:$G$40`
- `comps_pe` => `'Comps'!$F$8:$F$40`
- `comps_peer_names` => `'Comps'!$C$8:$C$40`
- `comps_peer_tickers` => `'Comps'!$B$8:$B$40`
- `comps_table` => `'Comps'!$B$8:$G$40`
- `comps_target_ebit_ttm` => `'Comps'!$C$5`
- `comps_target_rev_ttm` => `'Comps'!$C$4`
- `IN_Beta` => `'Inputs'!C39`
- `IN_ERP` => `'Inputs'!C38`
- `IN_Price` => `'Inputs'!C54`
- `IN_RiskFreeRate` => `'Inputs'!C37`
- `IN_TaxRate` => `'Inputs'!C27`
- `IN_TerminalGrowth` => `'Inputs'!C44`
- `IN_Ticker` => `'Inputs'!C4`
- `inp_base_g1` => `'Inputs'!C20`
- `inp_base_g2` => `'Inputs'!C21`
- `inp_base_g3` => `'Inputs'!C22`
- `inp_base_g4` => `'Inputs'!C23`
- `inp_base_g5` => `'Inputs'!C24`
- `inp_base_gt` => `'Inputs'!C44`
- `inp_base_m10` => `'Inputs'!C26`
- `inp_base_m5` => `'Inputs'!C25`
- `inp_base_tax` => `'Inputs'!C27`
- `inp_base_wacc` => `'Inputs'!C43`
- `inp_basic_shares` => `'Inputs'!C53`
- `inp_beta` => `'Inputs'!C39`
- `inp_cap_lease_toggle` => `'Inputs'!C59`
- `inp_cap_rd_toggle` => `'Inputs'!C58`
- `inp_capex_pct` => `'Inputs'!C29`
- `inp_capex_ttm` => `'Inputs'!C13`
- `inp_cash` => `'Inputs'!C49`
- `inp_da_pct` => `'Inputs'!C28`
- `inp_da_ttm` => `'Inputs'!C12`
- `inp_debt` => `'Inputs'!C50`
- `inp_dNWC_ttm` => `'Inputs'!C14`
- `inp_dw` => `'Inputs'!C42`
- `inp_ebit_ttm` => `'Inputs'!C10`
- `inp_erp` => `'Inputs'!C38`
- `inp_g1` => `'Inputs'!C20`
- `inp_g2` => `'Inputs'!C21`
- `inp_g3` => `'Inputs'!C22`
- `inp_g4` => `'Inputs'!C23`
- `inp_g5` => `'Inputs'!C24`
- `inp_gt` => `'Inputs'!C44`
- `inp_kd` => `'Inputs'!C41`
- `inp_m10` => `'Inputs'!C26`
- `inp_m5` => `'Inputs'!C25`
- `inp_name` => `'Inputs'!E4`
- `inp_nwc_pct` => `'Inputs'!C30`
- `inp_opt_g1` => `'Inputs'!I20`
- `inp_opt_g2` => `'Inputs'!I21`
- `inp_opt_g3` => `'Inputs'!I22`
- `inp_opt_g4` => `'Inputs'!I23`
- `inp_opt_g5` => `'Inputs'!I24`
- `inp_opt_gt` => `'Inputs'!I44`
- `inp_opt_m10` => `'Inputs'!I26`
- `inp_opt_m5` => `'Inputs'!I25`
- `inp_opt_tax` => `'Inputs'!I27`
- `inp_opt_wacc` => `'Inputs'!I43`
- `inp_other_adj` => `'Inputs'!C52`
- `inp_pess_g1` => `'Inputs'!G20`
- `inp_pess_g2` => `'Inputs'!G21`
- `inp_pess_g3` => `'Inputs'!G22`
- `inp_pess_g4` => `'Inputs'!G23`
- `inp_pess_g5` => `'Inputs'!G24`
- `inp_pess_gt` => `'Inputs'!G44`
- `inp_pess_m10` => `'Inputs'!G26`
- `inp_pess_m5` => `'Inputs'!G25`
- `inp_pess_tax` => `'Inputs'!G27`
- `inp_pess_wacc` => `'Inputs'!G43`
- `inp_px` => `'Inputs'!C54`
- `inp_rd_pct` => `'Inputs'!C31`
- `inp_rd_ttm` => `'Inputs'!C15`
- `inp_rent_pct` => `'Inputs'!C32`
- `inp_rent_ttm` => `'Inputs'!C16`
- `inp_rev_ttm` => `'Inputs'!C9`
- `inp_rf` => `'Inputs'!C37`
- `inp_tax_norm` => `'Inputs'!C27`
- `inp_tax_ttm` => `'Inputs'!C11`
- `inp_ticker` => `'Inputs'!C4`
- `inp_tsm_tranche1_count_mm` => `'Dilution (TSM)'!$C$9`
- `inp_tsm_tranche1_note` => `'Dilution (TSM)'!$G$9`
- `inp_tsm_tranche1_strike` => `'Dilution (TSM)'!$D$9`
- `inp_tsm_tranche1_type` => `'Dilution (TSM)'!$E$9`
- `inp_w_base` => `'Inputs'!H63`
- `inp_w_opt` => `'Inputs'!I63`
- `inp_w_pess` => `'Inputs'!G63`
- `log_actions_firstrow` => `'Agent Log'!$B$17:$J$17`
- `log_actions_header` => `'Agent Log'!$B$16:$J$16`
- `log_agent_version` => `'Agent Log'!$E$9`
- `log_assumptions_firstrow` => `'Agent Log'!$B$221:$K$221`
- `log_assumptions_header` => `'Agent Log'!$B$220:$K$220`
- `log_cost_usd` => `'Agent Log'!$E$12`
- `log_currency_units` => `'Agent Log'!$E$11`
- `log_data_sources` => `'Agent Log'!$C$11`
- `log_end_ts` => `'Agent Log'!$E$7`
- `log_engine` => `'Agent Log'!$E$10`
- `LOG_Entries` => `'Agent Log'!$B$16:$J$216`
- `log_model` => `'Agent Log'!$C$10`
- `log_run_id` => `'Agent Log'!$C$6`
- `log_start_ts` => `'Agent Log'!$C$7`
- `log_status` => `'Agent Log'!$E$6`
- `log_story_firstrow` => `'Agent Log'!$B$251:$J$251`
- `log_story_header` => `'Agent Log'!$B$250:$J$250`
- `log_template_version` => `'Agent Log'!$C$9`
- `log_tokens` => `'Agent Log'!$C$12`
- `out_diluted_shares` => `'Output'!$C$14`
- `out_enterprise_value` => `'Output'!$C$8`
- `out_enterprise_value_weighted` => `'Output'!$C$8`
- `OUT_EnterpriseValue` => `'Output'!$C$8`
- `out_equity_value` => `'Output'!$C$7`
- `out_equity_value_weighted` => `'Output'!$C$7`
- `OUT_EquityValue` => `'Output'!$C$7`
- `out_run_id` => `'Output'!$C$5`
- `out_terminal_g` => `'Output'!$C$10`
- `out_terminal_g_base` => `'Inputs'!C44`
- `out_terminal_g_opt` => `'Inputs'!I44`
- `out_terminal_g_pess` => `'Inputs'!G44`
- `OUT_TerminalValue` => `'DCF'!$C$33`
- `out_tsm_diluted_shares` => `'Dilution (TSM)'!$C$25`
- `out_tsm_incremental_shares` => `'Dilution (TSM)'!$C$24`
- `out_value_per_share` => `'Output'!$C$6`
- `out_value_ps_base` => `'Output'!$C$16`
- `out_value_ps_opt` => `'Output'!$C$17`
- `out_value_ps_pess` => `'Output'!$C$15`
- `out_value_ps_weighted` => `'Output'!$C$6`
- `OUT_ValuePerShare` => `'Output'!$C$6`
- `out_wacc` => `'Output'!$C$9`
- `OUT_WACC` => `'Output'!$C$9`
- `out_wacc_base` => `'Inputs'!C43`
- `out_wacc_opt` => `'Inputs'!I43`
- `out_wacc_pess` => `'Inputs'!G43`
- `sens_base_value_ps` => `'Sensitivity'!$C$4`
- `sens_grid_full` => `'Sensitivity'!$B$6:$G$11`
- `sens_grid_header` => `'Sensitivity'!$B$6:$G$6`
- `sens_grid_values` => `'Sensitivity'!$C$7:$G$11`
- `sens_terminal_g_vector` => `'Sensitivity'!$C$6:$G$6`
- `sens_wacc_vector` => `'Sensitivity'!$B$7:$B$11`
- `story_grid_citations` => `'Story'!$G$24:$G$26`
- `story_grid_header` => `'Story'!$B$23:$G$23`
- `story_grid_rows` => `'Story'!$B$24:$G$26`
- `story_core_narrative_rows` => `'Story'!$C$24:$C$26`
- `story_growth` => `'Story'!$B$8`
- `story_kpi_to_track_rows` => `'Story'!$E$24:$E$26`
- `story_linked_operating_driver_rows` => `'Story'!$D$24:$D$26`
- `story_memo_hooks` => `'Story'!$C$28:$G$30`
- `story_profitability` => `'Story'!$B$11`
- `story_reinvestment` => `'Story'!$B$14`
- `story_risk` => `'Story'!$B$17`
- `story_sanity_checks` => `'Story'!$B$20`
- `story_thesis` => `'Story'!$B$5`
- `tsm_tranche_header` => `'Dilution (TSM)'!$B$8:$G$8`
- `tsm_tranche_table` => `'Dilution (TSM)'!$B$9:$G$20`
<!-- TEMPLATE_NAMED_RANGES_END -->

## Planned named-range delta (to add on Google template)
This is the required named-range extension to support variable peer count and variable industry-specific multiple sets while remaining named-range-only.

Comps dynamic grid:
1. `comps_header` => `'Comps'!$B$7:$AZ$7` (expand existing range from fixed-width to dynamic-width capacity).
2. `comps_firstrow` => `'Comps'!$B$8:$AZ$8`.
3. `comps_table` => `'Comps'!$B$8:$AZ$200` (expand existing body range for arbitrary peers and multiple columns).
4. `comps_table_full` => `'Comps'!$B$7:$AZ$200`.
5. `comps_peer_tickers` => `'Comps'!$B$8:$B$200` (expand existing peer capacity).
6. `comps_peer_names` => `'Comps'!$C$8:$C$200` (expand existing peer capacity).
7. `comps_multiples_header` => `'Comps'!$C$7:$AY$7` (model writes industry-specific multiple names here, between `Ticker` and `Notes`).
8. `comps_multiples_values` => `'Comps'!$C$8:$AY$200` (model writes peer x multiple valuation matrix here, between `Ticker` and `Notes`).
9. `comps_method_note` => `'Comps'!$C$6` (records chosen multiple framework and inclusion logic).
10. `comps_peer_count` => `'Comps'!$F$4` (actual populated data rows, including target row).
11. `comps_multiple_count` => `'Comps'!$F$5` (actual multiple columns populated).

Comps runtime write contract (mandatory):
1. Write a single rectangular comps block using `sheets_write_named_table` with `table_name=comps_table_full`.
2. Header row starts at `Comps!B7`:
- first non-empty header must be `Ticker`.
- last non-empty header must be `Notes`.
- every header between those two is a model-selected industry-specific comparison metric.
3. First data row starts at `Comps!B8` and must be the target ticker for the run.
4. Data must be consecutive between `Ticker` and `Notes` columns (no interior gaps).
5. Do not use `sheets_append_named_table_rows` for `Comps` table population.

Structured table anchors for deterministic writes:
1. `sources_header` => `'Sources'!$B$6:$L$6`
2. `sources_firstrow` => `'Sources'!$B$7:$L$7`
3. `sources_table` => `'Sources'!$B$7:$L$400`
4. `log_actions_table` => `'Agent Log'!$B$17:$J$216`
5. `log_assumptions_table` => `'Agent Log'!$B$221:$K$246`
6. `log_story_table` => `'Agent Log'!$B$251:$J$286`
7. `checks_statuses` => `'Checks'!$C$5:$C$17` (hard-stop publish gate statuses).

Story down-column anchors (approved):
1. `story_thesis` => `'Story'!$B$5`
2. `story_growth` => `'Story'!$B$8`
3. `story_profitability` => `'Story'!$B$11`
4. `story_reinvestment` => `'Story'!$B$14`
5. `story_risk` => `'Story'!$B$17`
6. `story_sanity_checks` => `'Story'!$B$20`

Story scenario-linkage anchors (mandatory for memo quality):
1. `story_core_narrative_rows` => `'Story'!$C$24:$C$26`
2. `story_linked_operating_driver_rows` => `'Story'!$D$24:$D$26`
3. `story_kpi_to_track_rows` => `'Story'!$E$24:$E$26`
4. `story_grid_rows` => `'Story'!$B$24:$G$26` (must include non-empty linkage fields for Pessimistic/Neutral/Optimistic rows)
5. `story_memo_hooks` => `'Story'!$C$28:$G$30` (claim-to-range hooks required before final memo completion)

Sources schema contract (approved, fixed order in `B:L`):
1. `field_block`
2. `source_type`
3. `dataset_doc`
4. `url`
5. `as_of_date`
6. `notes`
7. `metric`
8. `value`
9. `unit`
10. `transform`
11. `citation_id`

Migration note:
1. Keep `comps_ev_ebit`, `comps_ev_sales`, `comps_pe`, and `comps_notes` as backward-compatible aliases during transition.
2. Runtime logic must prioritize `comps_multiples_header` + `comps_multiples_values` over fixed-multiple aliases.

## Anthropic skills patterns adopted (design basis)
Based on Anthropic Agent Skills and Claude Code skills docs, V1 adopts these principles:
- Skills are filesystem modules with `SKILL.md` + optional supporting files.
- Progressive disclosure: keep metadata concise, load detailed references/scripts on demand.
- Strong skill descriptions: description text drives automatic invocation quality.
- Invocation control:
  - `disable-model-invocation` for dangerous/manual-only workflows
  - `user-invocable` for hidden background skills
- Tool scoping:
  - In Claude Code CLI, skill-level `allowed-tools` can constrain active tools.
  - In SDK patterns, constrain tools at runtime `allowed_tools` configuration.
- Subagent/fork context for isolated heavy research tasks when appropriate.

## Finance skill set to provide the agent
The following skills should be created and available to the multi-turn agent.

1. `ticker-intake-and-mandate`
- Captures objective, horizon, style constraints, and missing high-impact inputs.
- Produces structured run brief.

2. `sec-filings-and-xbrl-extraction`
- Pulls and normalizes 10-K/10-Q/8-K and key XBRL facts.
- Writes source-backed fundamentals to sheet staging areas.

3. `market-and-fundamentals-harvest`
- Pulls price, shares, estimates, profitability, and operating metrics.
- Harmonizes units/periods with filing-derived data.

4. `rates-and-macro-context`
- Pulls risk-free curve and macro regime context (FRED/Treasury).
- Produces discounting context block with citations.

5. `transcript-and-guidance-analysis`
- Pulls earnings call/transcript and guidance language.
- Extracts directional signals for scenario assumptions.

6. `corporate-actions-and-cap-table`
- Pulls buybacks, splits, dilution events, debt events.
- Reconciles with TSM and share-count assumptions.

7. `peer-set-and-competitive-analysis`
- Builds and justifies an industry-specific peer set (not generic mega-cap set).
- Generates competitive positioning and relative valuation context.
- Uses canonical dataset first; requests missing company/peer fields when needed.
- May invoke deterministic Python math execution for intermediate multiple calculations before tabular sheet writes.

8. `assumption-engine-pess-base-opt`
- Produces scenario assumption vectors for all key drivers.
- Sets and explains scenario weights.

9. `sheets-dcf-executor`
- Writes scenario inputs to template, triggers calculation, reads outputs.
- Enforces no-offsheet-math policy.

10. `sensitivity-engine`
- Populates sensitivity tables and selected stress cases.
- Flags nonlinear fragility in valuation outputs.

11. `story-to-valuation-linker`
- Maps qualitative story to quantitative assumptions and outputs.
- Forces explicit “what must be true” + disconfirming evidence.

12. `citation-and-consistency-auditor`
- Verifies every material numeric claim has source mapping.
- Detects contradiction across tools and missing provenance.

13. `memo-composer-ib-style`
- Produces final memo in professional IB structure and tone.
- Uses weighted scenario framing and risk/catalyst matrix.

14. `publish-and-logbook-closeout`
- Final run checks, status set, artifact links, run summary append.
- Manual-invocation-only in production if needed.

## Skill-to-template alignment (mandatory)
1. `ticker-intake-and-mandate`
- Writes run metadata and mandate assumptions to `Agent Log` and `Inputs` (`inp_ticker`, `inp_name`).

2. `sec-filings-and-xbrl-extraction`
- Populates filing-derived financial inputs in `Inputs`; records source links in `Sources`; logs extraction actions in `Agent Log`.

3. `market-and-fundamentals-harvest`
- Updates market-linked ranges (`inp_px`, share/debt/cash-related ranges) and reconciles with `Dilution (TSM)` and `DCF`.

4. `rates-and-macro-context`
- Updates `inp_rf`, `inp_erp`, and rate/macro citation rows in `Sources`; logs rationale in `Agent Log`.

5. `transcript-and-guidance-analysis`
- Writes management guidance signals to `Story`; maps implication notes to scenario assumptions journal rows.

6. `corporate-actions-and-cap-table`
- Updates dilution/debt/lease relevant fields (`Dilution (TSM)`, `Lease Capitalization`, cash/debt/share ranges).

7. `peer-set-and-competitive-analysis`
- Populates `Comps` and competitive narrative components in `Story`; links source provenance in `Sources`.

8. `assumption-engine-pess-base-opt`
- Writes all scenario vectors to `inp_pess_*`, `inp_base_*`, `inp_opt_*` and weights (`inp_w_*`), with explicit rationale logs.

9. `sheets-dcf-executor`
- Triggers sheet recalculation flow and reads outputs from `Output` named ranges only; no off-sheet valuation math.

10. `sensitivity-engine`
- Populates `Sensitivity` scenarios and shock grids referencing active scenario assumptions and output ranges.

11. `story-to-valuation-linker`
- Ensures `Story` assumptions reconcile to `Inputs`/`Output` and records “what must be true” links.

12. `citation-and-consistency-auditor`
- Validates every material number in `Story`/memo is backed by `Sources` and sheet outputs; flags contradictions in `Checks`.

13. `memo-composer-ib-style`
- Drafts memo using `Story`, `Comps`, `Sensitivity`, and `Output` ranges with explicit source mapping.

14. `publish-and-logbook-closeout`
- Sets final status (`log_status`), writes end timestamp, verifies logbook completeness, and stamps artifact readiness.

## Mandatory tool stack for V1 (all to be implemented)
V1 now treats all previously “recommended” tools as in-scope mandatory integrations.

1. Google Sheets API
- Template copy, named-range writes, formula execution/read, log append.
- Authentication mode for V1 is Google OAuth user login (not service-account mode).

2. SEC EDGAR/XBRL
- Filings metadata, submissions, companyfacts, filing section extraction.

3. Market/fundamentals provider (Finnhub primary)
- Price, shares, statements, estimates, basic market intelligence.

4. Web/news search
- Catalyst/risk/news flow and source-backed narrative evidence.
- Tavily is the primary web-search API for open-web retrieval.

5. Rates/macro provider (FRED/Treasury)
- Risk-free and macro indicators for discount-rate context.

6. Earnings transcript provider
- Call transcript and management commentary extraction.

7. Corporate actions provider
- Splits, buybacks, dividend policy, issuance events.

8. Sector/peer classification provider
- Industry mapping and peer universe scaffolding.

9. Source contradiction checker
- Cross-source conflict detection and confidence scoring.

10. Deterministic Python math executor
- Allows LLM-directed creation/execution of bounded Python functions for intermediate calculations.
- Primary use in V1: industry-specific comps math, peer ranking, and tabular multiple preparation.
- Must log code hash, inputs, outputs, and execution timestamp in run traces.
- Must not produce final valuation outputs that bypass sheet formulas.

## Provider strategy (agreed mixed approach)
As of February 15, 2026, V1 uses a mixed provider strategy to maximize free-tier utility while preserving research quality.

1. SEC EDGAR/XBRL is authoritative for filing-grounded financial facts.
- Use SEC as primary truth source for filings and XBRL concepts.
- Use vendor outputs only as convenience unless reconciled to SEC data.

2. Finnhub is primary for market/fundamentals/news/peers.
- Primary endpoints include quote/profile/basic financials/financials-reported/company-news/company-peers.
- Finnhub supports most day-to-day ingestion flows with better free-tier throughput than Alpha Vantage.

3. Tavily is primary for web search.
- Use Tavily for open-web retrieval, catalyst discovery, and external evidence gathering beyond market-data feeds.
- Keep source URLs and fetch timestamps for every Tavily-derived claim.

4. Alpha Vantage is scoped to transcript and corporate-action gaps.
- Use Alpha Vantage primarily for earnings call transcript retrieval and corporate-action supplementation.
- Keep Alpha Vantage calls budgeted and cached because free-tier daily call limits are tight.

5. FRED/Treasury remain primary for rates and macro.
- Use FRED/Treasury for risk-free and macro context instead of equity-data vendors.

6. Contradiction checker is internal.
- Implement rule-based contradiction checks across SEC, Finnhub, Alpha Vantage, and web/news evidence.
- Route conflicts to `Checks` + `Sources` with confidence and source priority labels.

## Source priority and fallback policy
1. Source trust order
- `SEC/FRED/Treasury` > `Alpha Vantage` > `Finnhub` > `web/news`.

2. Fallback behavior
- If Finnhub lacks a required field, use Alpha Vantage fallback where available.
- If neither vendor source is reliable, ask user for a decision-ready assumption and log judgment explicitly.

3. Caching and cost control
- Cache by `ticker + endpoint + period` for vendor APIs.
- Reserve Alpha Vantage calls for high-value steps (transcripts and corporate actions).
- Log call counts and provider usage in run metadata.

## Google OAuth policy for Sheets access
1. Required auth mode
- V1 must authenticate to Google Sheets/Drive through OAuth user login.
- Service-account auth is out-of-scope for V1 run execution.

2. Required environment variables
- `GOOGLE_AUTH_MODE=oauth`
- `GOOGLE_OAUTH_CLIENT_SECRET_FILE`
- `GOOGLE_OAUTH_TOKEN_FILE`

3. Operational behavior
- On first run, user completes OAuth consent and token is stored in `GOOGLE_OAUTH_TOKEN_FILE`.
- Subsequent runs reuse refreshed OAuth credentials for template copy, range writes, output reads, and logbook append.

## Tool implementation standards
- Every tool has strict JSON schema input/output contracts.
- Every tool response includes provenance fields:
  - source
  - endpoint/document id
  - timestamp
  - unit metadata (where relevant)
- Retries, timeouts, and error taxonomy are standardized in shared tool middleware.
- Tool outputs are normalized into a canonical data model before sheet writes.
- Provider adapters must emit normalized fields regardless of source so skills remain source-agnostic.
- Python math tool runs with deterministic settings and bounded runtime/memory, with full execution logs captured per call.

## Phase 1: Foundation and contracts
- Freeze spreadsheet tab/named-range contract.
- Implement template copy + run metadata registration.
- Add contract validator (fail fast if required tabs/ranges missing).
- Implement shared tool adapter framework and canonical data model.
- Integrate mandatory tools 1–4 (Sheets, SEC, fundamentals, web/news).

## Phase 2: Full data stack integration
- Integrate mandatory tools 5–9 (rates, transcripts, corp actions, sector/peer, contradiction checker).
- Add source confidence and contradiction flags to data pipeline.
- Add data-quality checks (period alignment, unit normalization, stale data checks).

## Phase 3: Multi-turn orchestration
- Build orchestrator state machine:
  - intake -> data collection -> data checks -> assumptions -> model run -> validation -> memo -> publish
- Add strict tool invocation policy and loop/time/budget guards.
- Add follow-up question flow for missing/ambiguous high-impact inputs.
- Add skill-routing layer that maps turn intent to finance skills.
- Add canonical-or-fetch branch for comps data:
  - use canonical dataset fields when available
  - fetch missing company/peer fields via tools
  - compute intermediate multiples in Python tool
  - write structured comps table into `Comps`

## Phase 4: Scenario valuation engine
- Implement 3 scenario assumption writing:
  - pessimistic
  - neutral/base
  - optimistic
- Implement scenario weights in-sheet.
- Read per-scenario and weighted outputs from sheet-only output ranges.
- Add hard checks:
  - WACC > g per scenario
  - g <= rf per scenario
  - weights sum check
  - weighted-output formula linkage
  - output completeness

## Phase 5: Story, sensitivities, comps, and memo quality
- Add competitive analysis and peer sanity checks using industry-specific peer sets.
- Add sensitivity tables/charts.
- Add story-to-valuation linkage only after quantitative steps are complete:
  - narrative
  - drivers
  - what must be true
  - disconfirming risks
- Enforce memo numeric grounding to sheet outputs.
- Enforce citation completeness and claim-source mapping.

## Phase 6: Logging, evals, and hardening
- In-sheet logs:
  - Action Ledger
  - Assumption Journal
  - Story Journal
- System traces:
  - tool calls, sheet mutations, validations, outputs
- Eval suite:
  - tool-call correctness
  - citation coverage
  - template contract compliance
  - scenario consistency
  - memo grounding checks
  - contradiction resolution quality
- Release gates: fail on invariant/citation/contract/tooling violations.

## Immediate remediation plan (post smoke `smoke_20260215T124043Z`)
The next implementation slice is a reliability hardening track before additional feature expansion.

### R0. Canonical dataset first, then sheet copy/prefill, then LLM
New required run order:
1. Build canonical dataset first for ticker using provider stack.
2. Persist dataset artifact at:
   - `artifacts/canonical_datasets/{TICKER}_canonical_dataset_{YYYYMMDDTHHMMSSZ}.json`
3. Validate canonical dataset required fields before sheet creation:
   - minimum: `inp_rev_ttm`, `inp_ebit_ttm`, `inp_tax_ttm`, `inp_cash`, `inp_debt`, `inp_basic_shares`, `inp_px`, `inp_rf`, `inp_tsm_tranche1_count_mm`, `inp_tsm_tranche1_type`.
4. Copy Google Sheets template for run.
5. Immediately prefill baseline TTM + TSM + run metadata via named ranges in copied sheet.
6. For comps, use canonical dataset for company/peers when available; otherwise request missing company/peer data before comps math.
7. Only after prefill hand the copied sheet (`spreadsheet_id`) to LLM phase loop.

Acceptance criteria:
- Every run log has canonical dataset path + checksum.
- `Inputs` TTM baseline is populated before first LLM phase starts.
- `Dilution (TSM)` prefill ranges are written before first LLM phase: `inp_tsm_tranche1_count_mm`, `inp_tsm_tranche1_type`, `inp_tsm_tranche1_note`.
- No phase starts with blank core TTM fields unless explicitly flagged as degraded mode.

### R0A. Robust canonical dataset contract (must be expanded beyond minimal hydration)
Canonical dataset must be an IB-grade research packet, not just a 36-range prefill object.

Required top-level sections:
1. `metadata`
- run/ticker/provider metadata, generation timestamp, dataset version, checksum.
2. `company_profile`
- legal name, ticker, exchange, country, reporting currency, sector, industry, sub-industry, fiscal-year-end.
3. `ttm_core`
- normalized TTM drivers required by template (`revenue`, `ebit`, `tax`, `da`, `capex`, `dNWC`, `rd`, `rent`, `cash`, `debt`, `shares`, `price`) with units and source tags.
4. `financial_history`
- annual panel (minimum 5 years) and quarterly panel (minimum 12 quarters) for key IS/BS/CF lines.
5. `market_pack`
- spot price, market cap, shares outstanding, beta, liquidity/volume context, 52-week range metadata when available.
6. `rates_pack`
- risk-free term points (as available), ERP assumption basis, debt cost basis, debt-weight basis.
7. `capital_structure`
- debt components, lease-related obligations summary, dilution/SBC context, buyback/split context (if available).
8. `rd_lease_inputs`
- fields specifically needed to run `R&D Capitalization` and `Lease Capitalization` tabs with explicit fallback rules.
9. `peer_pack`
- industry-specific peer universe with company + peer fields required for EV/Sales, EV/EBITDA, P/E, and FCF-yield style comps math.
10. `research_pack`
- transcript signals, corporate actions, catalyst/risk news, and contradiction-check outputs.
11. `quality_report`
- per-field missingness, staleness timestamp checks, unit normalization status, confidence score, and fallback usage.
12. `citations`
- source, endpoint/document ID, URL, access timestamp, unit notes.
13. `sheets_prefill`
- named-range payload for initial `Inputs` hydration only (formula-owned output ranges excluded).

Execution policy:
1. Build `canonical_dataset` and persist artifact before sheet copy.
2. Validate `quality_report` gates before sheet hydration.
3. Hydrate `sheets_prefill` named ranges immediately after copy.
4. Expose full canonical packet to LLM tools for comps/research/story phases.

Acceptance criteria:
- Canonical artifact includes all required sections above.
- `peer_pack` is populated for industry-specific comps or explicitly flagged degraded with reason.
- `quality_report` is present and machine-checkable.
- LLM phase loop receives canonical dataset reference + checksum in run context.

### R1. Enforce strict Sheets address discipline in code (not prompt-only)
1. Add server-side validator for named-range tools:
   - allow only existing named ranges for `sheets_write_named_ranges` / `sheets_read_named_ranges`.
   - reject A1 tokens and pseudo-ranges (`Sources_A2`, `Story_B10`, `Inputs!C20`, `Story_Growth`).
2. Validate target tab names against workbook tab whitelist.
3. Return structured validation errors to model without hitting Google API.

Acceptance criteria:
- Zero Google API “Unable to parse range” errors in smoke runs.
- Invalid addresses are blocked locally with explicit remediation message.

### R2. Null-safe optional numeric tool args
1. Replace direct `int(payload.get(...))` with null-safe coercion helper for:
   - `fetch_news_evidence.limit`
   - `discover_peer_universe.limit`
   - `fetch_transcript_signals.limit`
   - `fetch_corporate_actions.limit`
   - `fetch_research_packet.news_limit`
2. Default when arg is absent or `null`.

Acceptance criteria:
- Zero `TypeError: int(None)` across smoke logs.

### R3. Protect formula-owned ranges
1. Add denylist for writes into output/formula-owned ranges (`out_*`, `calc_*`) except explicit maintenance operations.
2. Add post-write integrity check:
   - `Output`, `Checks`, `Sensitivity` must have no `#REF!`/`#N/A` for required contract cells.
3. Fail run immediately on integrity breach (hard-stop policy).

Acceptance criteria:
- No contract output cell contains formula errors at publish.
- Checks cannot report PASS when required output cells are broken.

### R4. Structured table-writing tools for log/sources/comps/story
1. Introduce table-safe named-table tools (append/update by named table), avoiding free-form ad hoc range strings for these tabs:
   - `Agent Log`, `Sources`, `Comps`, `Story`.
2. Use only `sheets_write_named_table` and `sheets_append_named_table_rows` for runtime table writes.
3. For comps, write company + peer multiples as structured row/column tables (no JSON-in-cell dumps).

Acceptance criteria:
- No JSON blobs dumped into single worksheet cells for table sections.
- Logbook and source records are row-structured and queryable.

### R5. Runtime guardrails for hangs
1. Add per-turn LLM timeout and per-phase wall-clock timeout.
2. If timeout occurs, mark phase degraded/failed with explicit reason and continue/fail per policy.

Acceptance criteria:
- No smoke run stalls indefinitely in a phase.
- Timeout reason is visible in run log and final notes.

### R6. Smoke test gate (AAPL) before marking V1 ready
Required smoke gate sequence:
1. canonical dataset generated and stored.
2. copied sheet has prefilled TTM baseline before LLM.
3. no parse-range errors.
4. no `int(None)` errors.
5. no formula-error cells in required outputs.
6. run reaches finalize and appends logbook row.

### R7. Industry-specific comps pipeline with Python math + sheet table writes
1. Identify industry/sub-industry classification for ticker and build justified peer set.
2. Pull company + peer canonical fields required for selected multiples; fetch missing fields via tool calls.
3. Let the model choose industry-appropriate multiple set (for example EV/EBITDA, EV/EBIT, EV/Sales, P/E, P/B, P/TBV, P/CF, FCF yield, EV/GP), then execute deterministic Python function(s) to compute the matrix and summary statistics.
4. Write outputs as a structured, dynamic table into `Comps` using named ranges:
   - peer rows can vary by run.
   - multiple columns can vary by industry and run.
   - header must be `Ticker` first, `Notes` last, dynamic multiples in-between.
   - table target is `comps_table_full` (header + data in one write).
   - first data row must be the target ticker.
5. Validate table completeness and alignment before proceeding to Story phase.

Acceptance criteria:
- Comps table is fully tabular and industry-specific.
- Comps supports variable peer count and variable multiple columns without contract changes.
- Python execution trace is logged for every comps-math run.
- Story phase starts only after comps + sensitivity + integrity checks complete.

### Implementation status update (2026-02-16)
This section records what has already been implemented in code for the R0-R7 remediation track.

Completed now:
1. Provider/tool surface cleanup (phase-v1 alignment)
- Removed non-V1 runtime fallback branches from provider factory:
  - dropped `placeholder` and `static` provider options in `backend/app/tools/provider_factory.py`.
- Removed placeholder client implementations/exports from:
  - `backend/app/tools/news/client.py`
  - `backend/app/tools/rates/client.py`
  - `backend/app/tools/peer/client.py`
  - `backend/app/tools/transcripts/client.py`
  - `backend/app/tools/corporate_actions/client.py`
  - `backend/app/tools/news/__init__.py`
  - `backend/app/tools/rates/__init__.py`
  - `backend/app/tools/peer/__init__.py`
  - `backend/app/tools/transcripts/__init__.py`
  - `backend/app/tools/corporate_actions/__init__.py`
  - `backend/app/tools/market/__init__.py`
- Removed unused LLM sheet tools from registry:
  - `sheets_copy_template`
  - `sheets_append_logbook_run`
  in `backend/app/tools/llm_tools.py`.

2. R1 strict Sheets address discipline in code
- Added server-side range validation in `backend/app/sheets/google_engine.py` for:
  - named-range writes (`_validate_named_range_write_targets`)
  - named-range reads (`read_named_ranges`)
  - named-table writes/appends (`write_named_table`, `append_named_table_rows`).
- Added spreadsheet schema caching (`_load_spreadsheet_schema`) for named ranges + bounded grid metadata + protected ranges.

3. R2 null-safe optional numeric tool args
- Replaced direct `int(payload.get(...))` patterns with:
  - `_coerce_optional_int`
  - `_coerce_optional_float`
  in `backend/app/tools/llm_tools.py`.
- Applied to:
  - `fetch_news_evidence.limit`
  - `fetch_transcript_signals.limit`
  - `fetch_corporate_actions.limit`
  - `discover_peer_universe.limit`
  - `fetch_research_packet.news_limit`
  - `python_execute_math.timeout_seconds`.

4. R3 formula-owned range protection (core guardrail)
- Added hard block on writes to formula-owned named ranges:
  - `out_*`
  - `calc_*`
  via `_is_formula_owned_name` in `backend/app/sheets/google_engine.py`.
- Added overlap detection to block A1 writes that intersect formula-owned named-range bounds:
  - `_overlaps_formula_owned`.

5. R4 structured table-writing tools
- Extended sheet engine contract in `backend/app/sheets/engine.py` with:
  - `append_named_table_rows(...)`
  - `write_named_table(...)`
- Implemented Google Sheets engine support in `backend/app/sheets/google_engine.py`.
- Added LLM tools in `backend/app/tools/llm_tools.py`:
  - `sheets_append_named_table_rows`
  - `sheets_write_named_table`
for row-structured writes in `Agent Log`, `Sources`, `Comps`, `Story`.

6. R7 deterministic Python math tool + orchestration wiring
- Added deterministic bounded Python executor module:
  - `backend/app/tools/python_math.py`
with AST validation, restricted builtins/modules, timeout, input/output size bounds, and trace metadata (`code_hash`, `input_hash`, timestamp, elapsed).
- Added LLM tool:
  - `python_execute_math`
in `backend/app/tools/llm_tools.py`.
- Wired Python math domain to orchestrator tool routing in:
  - `backend/app/orchestrator/langgraph_finance_agent.py`.
- Updated peer/comps skill wiring:
  - `backend/app/skills/catalog.py` (`peer-set-and-competitive-analysis` now requires `python_math`)
  - `skills/peer-set-and-competitive-analysis/SKILL.md` (explicit deterministic Python math + structured sheet table policy).

7. Orchestrator run-scope sheet guardrail
- Added `_enforce_sheet_tool_scope(...)` in `backend/app/orchestrator/langgraph_finance_agent.py` to force all `sheets_*` tool calls onto the active run `spreadsheet_id` (inject/override behavior).

8. R5 runtime hang guardrail (partial)
- Added per-phase wall-clock timeout guardrail:
  - `max_phase_wall_clock_seconds`
  in `backend/app/orchestrator/langgraph_finance_agent.py`.
- Timeout now records guardrail event and exits the phase loop with degraded note.

9. Stream E named-range-only runtime cleanup and refactor
- Removed deprecated A1 tools from LLM runtime:
  - `sheets_write_ranges`
  - `sheets_read_ranges`
  - `sheets_append_rows`
  - `sheets_write_table`
- Added named-range read tool:
  - `sheets_read_named_ranges`
- Updated orchestrator tool domain + phase extras to use named-range/named-table tools only.
- Updated skill contract and markdown for named-range-only policy:
  - `backend/app/skills/catalog.py`
  - `skills/google-sheets-range-discipline/SKILL.md`
  - `skills/google-sheets-range-discipline/references/workbook-range-contract.md`
  - `skills/peer-set-and-competitive-analysis/SKILL.md`
- Skill inventory audit:
  - no orphan skill directories detected outside catalog + shared quality bundle; no skill directory deletions required in this slice.

10. Google template named-range extension applied
- Added script:
  - `scripts/upsert_template_named_ranges.py`
- Applied to Drive template:
  - `Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook`
  - spreadsheet id: `1D6I5wn5jmHqXt5gemdqwN0I2eTdj5Ns4ZIHhheVDNwY`
- Result:
  - dynamic comps named ranges created/updated
  - sources + agent-log table anchors created
  - `Comps` column capacity expanded to `AZ` to support variable multiples.
  - `checks_statuses` range added for finalize hard-stop integrity gating.

11. Post-review contract/order/reliability fixes implemented
- Enforced dynamic comps + table-anchor ranges in workbook contract:
  - `backend/app/workbook/contract.py`
- Initialization now gates on canonical dataset readiness before template copy:
  - canonical prefill fetched/validated first, then sheet copy, then immediate prefill write.
  - implemented in `backend/app/orchestrator/langgraph_finance_agent.py`.
- Contract validation now runs against the copied Google run sheet (not local file assumptions):
  - uses `sheets_engine.inspect_workbook(...)` before any phase execution.
- Reassigned `peer-set-and-competitive-analysis` to run post-DCF in `validation` phase:
  - `backend/app/skills/catalog.py`.
- Added per-`model.invoke` timeout wrapper to prevent blocking hangs:
  - `max_llm_invoke_seconds` + guarded invocation in phase loop and planner fallback.
- Added finalize hard-stop integrity scan for formula errors + checks statuses:
  - scans `Output`/`Sensitivity` ranges and `checks_statuses`.
  - run fails if any error token or non-`PASS` checks status is found.

Validation completed:
1. Unit tests
- Full unit suite pass:
  - `PYTHONPATH=. uv run pytest -q tests/unit`
  - result: `27 passed`.

2. New/updated tests added
- `tests/unit/test_provider_factory.py` (rejects non-V1 provider names).
- `tests/unit/test_llm_tools.py` (new Python math + structured sheet tools coverage).
- `tests/unit/test_google_sheets_engine_ranges.py` (A1 parser + formula-overlap protections).
- `tests/unit/test_orchestrator_guardrails.py` (run-scoped spreadsheet ID enforcement).
- `tests/unit/test_workbook_contract.py` (dynamic comps + table-anchor + checks range contract regression).

Outstanding to finish in next slice:
1. R6 gate:
- End-to-end AAPL smoke gate sequence must still be rerun against these changes.

### AAPL smoke run critique + remediation plan (pending approval)
Run audited:
- run id: `smoke_20260216T063510Z`
- run sheet: `AAPL_smoke_20260216T063510Z_Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx`
- run log: `artifacts/run_logs/smoke_20260216T063510Z.log`

IB-manager critique (direct):
1. Model integrity is broken because circular-reference `#REF!` errors propagate through valuation outputs.
- `Inputs!C55`, `Dilution (TSM)!C14/F14/C24/C25`, multiple `DCF` output lines, `Sensitivity!C4`, `Output` headline cells, and `Checks` are contaminated.
2. Core TTM hydration quality is below investment-committee bar.
- `Inputs!C12`, `Inputs!C13`, `Inputs!C15`, `Inputs!C16` are blank; `Inputs!C14` is hard zero.
3. Comps and sensitivity deliverables are not produced at all.
- `Comps` has headers only; no peer table rows.
- `Sensitivity` still has placeholder text and no computed sweep.
4. Data provenance and audit trail writes are structurally misaligned.
- `Sources` and `Agent Log` rows are appended at top-left rather than inside intended tables.
5. Prompt/tool discipline is still weak in multi-turn behavior.
- LLM attempted malformed range targets (for example `Inputs!inp_base_wacc`, `Output!out_value_ps_base`) and attempted write into formula-owned range (`calc_diluted_shares`), which guardrails correctly blocked.
6. Named-range contract is inconsistent between template and skills.
- `out_wacc` is missing while `OUT_WACC` exists, causing avoidable tool-call failures.
7. Runtime reliability remains below smoke-gate standard.
- Run stalled in publish due blocking `model.invoke`; process required manual interrupt.

Root causes confirmed from sheet formulas:
1. Circular formula loop in `Dilution (TSM)`:
- `Inputs!C55 -> 'Dilution (TSM)'!C14`
- `'Dilution (TSM)'!C14 -> C25`
- `C25 -> C5 + C24`, while `C24 -> SUM(F9:F20)` and `F14` depends on `C14`.
2. Circular formula loop in `R&D Capitalization`:
- `C16:C18` feed from `C22:C24`
- `C22:C24` aggregate lines that depend back on rows using `C16:C18`.
3. Table-write strategy uses generic append operations instead of contract anchors/structured table targets.

Remediation plan status (2026-02-16):
1. Stream A complete: template circular-reference repair on Google template
- Template: `Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx` (Google Sheets).
- Fixed circular loops:
  - `Inputs!C55` now references `'Dilution (TSM)'!C25` (not `C14`).
  - `Output!C14` now references `Inputs!C55`.
  - cleared circular self-feed formulas in `'R&D Capitalization'!C16:C19`.
  - cleared `'Dilution (TSM)'!C14` formula to restore it as a pure input row.
- Post-fix template audit: `#REF!` count is `0`.

Remaining major issues from AMZN run (`smoke_20260216T122315Z`) to fix next:
1. Scenario value-per-share outputs were produced from a pre-fix copied sheet and remained `#REF!`.
2. `checks_statuses` still contained non-pass statuses, blocking finalize.
3. `Comps` table shape was inconsistent with headers/multiples (rows had narrative text, not full multiple matrix).
4. `Sources` rows were structurally inconsistent (mixed schema/types across columns).
5. Story evidence chain incomplete (`story_grid_citations` empty; reinvestment/sanity fields under-filled).
6. Transient provider failures (e.g., Finnhub 502) are not yet fully absorbed by deterministic fallback logic.

Planned remediation streams (pending approval):
1. Stream B: post-template-fix run integrity and formula hardening
- Re-run smoke from corrected template and validate required ranges:
  - `out_value_ps_pess/base/opt/weighted`
  - `sens_base_value_ps`, `sens_grid_values`, `checks_statuses`.
- Add finalize guard: fail if required output/check cells contain any error token (`#REF!`, `#N/A`, `#VALUE!`, `#DIV/0!`).
- Add run note classification to separate template faults vs data faults vs provider faults.

2. Stream C: comps quality contract (IB-grade)
- Contract synchronization rule (mandatory for this stream):
  - if any `comps_*` named-range address/shape changes, update in this order:
    1) Google template named ranges,
    2) skill manifests + skill markdown,
    3) tool validators/schemas,
    4) orchestrator allowlists/guards,
    5) tests and smoke assertions.
  - Do not ship partial contract changes.
- Enforce tabular comps contract:
  - header and row width must match.
  - row schema must be numeric multiple columns, not prose.
- Add deterministic comps writer:
  - peer discovery -> peer fundamentals/market fetch -> multiple computation in `python_execute_math` -> named-table write.
- Add hard gate:
  - minimum peer count met,
  - minimum multiple column count met,
  - no empty required multiples for target row.
- Peer comparison skill update required:
  - refresh `peer-set-and-competitive-analysis` workflow to enforce:
    - sector/industry + business-model + unit-economics screening,
    - explicit inclusion/exclusion rationale per peer,
    - computed multiples table (not narrative rows),
    - citations mapped into `sources_table` and `story_grid_citations`.
  - remove legacy guidance that permits low-information comps rows.

3. Stream D: sources + story auditability contract
- Contract synchronization rule (same as Stream C):
  - if any `sources_*`, `story_*`, `log_*`, or `checks_*` named-range addresses/shape change,
    update template -> skills -> tools -> orchestration -> tests in one release unit.
- Enforce `sources_table` schema typing/order (fixed `B:L`):
  - `field_block`, `source_type`, `dataset_doc`, `url`, `as_of_date`, `notes`, `metric`, `value`, `unit`, `transform`, `citation_id`.
- Enforce story completeness gate before publish:
  - `story_thesis`, `story_growth`, `story_profitability`, `story_reinvestment`, `story_risk`, `story_sanity_checks` non-empty.
  - `story_grid_citations` contains source IDs/URLs for each scenario row.
- Add contradiction results logging into `log_assumptions_table` with explicit action/resolution rows.

4. Stream E: provider fault tolerance
- Add endpoint-specific fallback in canonical/research packet assembly:
  - if one provider call fails transiently (502/503), continue with cached/previous successful block where permitted and mark confidence penalty.
- Add per-tool retry profile and structured degraded-mode notes to avoid silent quality drops.

5. Stream F: smoke gate upgrade
- Smoke passes only if all are true:
  - all phases completed,
  - required outputs numeric and finite,
  - `checks_statuses` all `PASS`,
  - comps/sensitivity/sources/story contracts satisfied,
  - no formula errors in required contract ranges.

Execution order after approval:
1. Re-run smoke on corrected template to establish clean baseline.
2. Implement Stream C (comps contract) and Stream D (sources/story contract) together.
3. Implement Stream E provider fault-tolerance.
4. Implement Stream B/F finalize+smoke hard gates.
5. Re-run smoke (AMZN then AAPL) and produce acceptance report.

Acceptance criteria for this remediation package:
1. Zero formula error tokens in required ranges at finalize.
2. `checks_statuses` all `PASS` for successful runs.
3. `Comps` populated as numeric tabular matrix with dynamic peer/multiple coverage.
4. `Sources` rows are schema-consistent and citation-usable.
5. Story fields and citation grid are complete and linked to assumptions/outputs.
6. Smoke tests pass only when structural + quant + auditability gates are all green.

Implementation update (2026-02-16, code-aligned):
1. Canonical artifact gating now enforced before sheet copy:
- `fetch_canonical_sheet_inputs` now persists canonical artifact JSON in `artifacts/canonical_datasets/` and returns:
  - `artifact_path`
  - `artifact_sha256`
  - `quality_report` (`missing_ranges`, `null_ranges`, `is_complete`)
- Initialization fails fast if metadata is missing or canonical completeness is false.

2. Data quality phase now has dedicated skill + deterministic hard gate:
- Added `skills/data-quality-gate-and-normalization/` and wired it to `data_quality_checks`.
- Orchestrator now runs deterministic pre-assumption checks on core inputs (`inp_rev_ttm`, `inp_ebit_ttm`, `inp_tax_ttm`, `inp_px`, `inp_rf`, `inp_erp`, `inp_beta`, `inp_basic_shares`), including plausibility bounds.
- If gate fails, run status is set to `FAILED` before assumptions.

3. Finalize now enforces full V1 publish contract:
- Required outputs include per-scenario and weighted outputs:
  - `out_value_ps_pess`, `out_value_ps_base`, `out_value_ps_opt`, `out_value_ps_weighted`, `out_equity_value_weighted`, `out_enterprise_value_weighted`.
- Scenario weights fail on missing/invalid cells (not only bad sums).
- Added hard checks for:
  - comps contract (`comps_peer_count`, `comps_multiple_count`, `comps_multiples_header`, numeric matrix coverage, target-row completeness),
  - sources schema quality (`sources_table` required columns + URL discipline + source diversity),
  - story completeness (`story_*` coverage + `story_grid_citations` completeness/format).

4. Provider degraded-mode handling strengthened:
- External research fetch tool failures (`fetch_research_packet`, transcript/news/actions/peer/contradiction checks) now return deterministic degraded payloads instead of crashing tool execution.
- `DataService` now treats news and citation collection as degradable (logs warning + continues) so canonical prefill is not blocked by non-core stream failures.

5. Workbook contract tightened:
- Added `sources_header` and `sources_firstrow` to required named-range contract in code.

6. Peer comparison skill updated:
- Explicitly enforces dynamic, sector-specific numeric multiples table discipline via `comps_multiples_header` and `comps_multiples_values`.
- Requires method note, peer screening rationale, and source-linked evidence rows.

7. Tool-call data artifact persistence added for agent runs:
- Every tool invocation now appends a JSONL record to:
  - `artifacts/canonical_datasets/<run_id>_tool_calls.jsonl`
- Coverage includes:
  - initialization canonical fetch tool call,
  - native Gemini tool-call loop invocations,
  - planner-executor fallback invocations (including rejected tool attempts).
- Each record captures:
  - `timestamp_utc`, `run_id`, `phase`, `tool`, `mode`, `status`, `guardrail`, `duration_ms`,
  - full `args`,
  - full `result` payload (or error payload).
- This creates a durable per-run audit trail of all tool input/output data under canonical artifacts.

### Named-range-only Google Sheets access policy (pending approval)
Target policy:
1. The LLM/agent must read and write Google Sheets data using named ranges only.
2. A1 ranges are disallowed for model-invoked tools.
3. Any A1 usage is treated as a contract violation and fails the run (or the phase, per policy).
4. The agent cannot read or edit arbitrary cells by row/column coordinates; every access must resolve to a pre-declared named-range contract.

Explicit access model (decision):
1. Allowed for agent runtime:
- named-range reads
- named-range writes
- named-range table appends/writes
2. Disallowed for agent runtime:
- any A1 notation (`Tab!A1`, `A1:B10`, etc.)
- row/column index addressing
- ad-hoc tab scans not tied to named ranges
3. Operator-only (non-agent) debug/maintenance access can remain separate, but is out of LLM runtime.

Why this is needed:
1. A1 generation is error-prone and caused repeated failures (`Inputs!inp_*`, `Output!out_*`, pseudo-ranges).
2. Named ranges create a stable contract between template, skills, tools, and orchestration.
3. This is required for reliable IB-style, auditable repeatability.

Required changes to execute this policy:
1. Template contract expansion (Google template first)
- Add named ranges for every cell/block the agent needs to read/write; no operational dependency on ad-hoc A1.
- Ensure all outputs have canonical + alias names where needed (for example both `out_wacc` and `OUT_WACC` if both are used).
- Add explicit table-body named ranges and row-anchor named ranges for:
  - `Sources`
  - `Agent Log` action/assumption/story tables
  - `Comps` table body
  - `Sensitivity` writable result block (if agent writes grid values).
- Align Story layout named ranges to approved down-column pattern (for example thesis starts at `B5` contract).

2. Tool surface changes
- Remove or disable model access to:
  - `sheets_read_ranges`
  - `sheets_write_ranges`
- Keep and harden:
  - `sheets_write_named_ranges`
- Add named-range-specific read/write tools (if needed) with strict schema:
  - `sheets_read_named_ranges` (list of names only)
  - `sheets_write_named_table` / `sheets_append_named_table_rows` using table-id enums that map to named ranges.
- A1-capable APIs may remain for operator/debug flows only, never exposed to LLM runtime.

3. Validation and enforcement
- Add hard validator: reject any target containing `!`, `:`, or A1-like tokens in LLM sheet tools.
- Enforce that every requested range exists in template named-range inventory.
- Enforce phase-specific named-range allowlists (read and write lists separately).
- Block formula-owned named-range writes (`out_*`, `calc_*`) unless explicitly operator-approved maintenance action.
- Add contract-level denylist in tool schemas so unsupported field names cannot bypass named-range validators.

4. Orchestration changes
- Update `_TOOL_DOMAIN_TO_REGISTRY` and phase tool set so LLM cannot call A1 tools.
- Update prompts/skills to remove A1 guidance and require named-range IDs exclusively.
- Add run metrics:
  - `named_range_calls_count`
  - `a1_calls_count` (must be zero for LLM flows).

5. Skill pack changes
- Update `google-sheets-range-discipline` to named-range-only rules.
- Update all skills that currently reference A1 table reads/writes to named-table contracts.
- Add explicit per-skill read/write named-range manifests.

6. Smoke/eval gate changes
- Fail smoke run if any LLM tool call uses A1 addresses.
- Fail smoke run if any requested named range is missing in copied sheet.
- Fail smoke run if any required named-range output is error-valued (`#REF!`, `#N/A`, `#VALUE!`).
- Add contract test that compares skill named-range manifests to live template named-range inventory.
- Emit explicit smoke metrics for contract quality:
  - `named_range_resolution_success_rate`
  - `named_range_missing_count`
  - `arbitrary_cell_access_attempt_count` (must be zero).

Proposed migration sequence:
1. Finalize named-range inventory on Google template (including table-body anchors and aliases).
2. Update workbook contract in code to match template inventory exactly.
3. Lock tool surface to named-range-only for LLM.
4. Update skills/prompts to named-range-only language.
5. Run AAPL smoke and confirm zero A1 calls + zero contract misses.

Acceptance criteria for named-range-only mode:
1. `a1_calls_count == 0` for all LLM phases.
2. 100% of LLM sheet reads/writes resolve to existing named ranges.
3. Zero invalid-range tool-call failures.
4. Zero formula errors in required output contract named ranges.
5. `Comps`, `Sensitivity`, `Sources`, and `Agent Log` are fully populated through named-range table contracts.

## Approved remediation plan (2026-02-17)
Scope approved in discussion:
1. Story narrative blocks move to down-column single-cell anchors (`story_thesis=B5`, `story_growth=B8`, `story_profitability=B11`, `story_reinvestment=B14`, `story_risk=B17`, `story_sanity_checks=B20`).
2. `Sources` table adopts fixed 11-column schema in `B:L`: `field_block`, `source_type`, `dataset_doc`, `url`, `as_of_date`, `notes`, `metric`, `value`, `unit`, `transform`, `citation_id`.
3. `Comps` must be written as one dynamic table from `Comps!B7` (`Ticker` first column, `Notes` last column, target ticker in first data row).

Execution order (mandatory):
1. Update Google template named ranges and visible headers first.
2. Update skill contracts (`google-sheets-range-discipline`, `peer-set-and-competitive-analysis`, `story-to-valuation-linker`, `citation-and-consistency-auditor`, `sensitivity-engine`) to enforce the new layout/schema.
3. Update orchestrator validation and tool-write discipline to enforce:
- story fields complete under new single-cell anchors.
- sources rows schema-valid in fixed column order.
- comps table contract (`comps_table_full` shape, header order, first-row target ticker) and control fields (`comps_peer_count`, `comps_multiple_count`, `comps_method_note`) must be present.
- sensitivity grid must be numeric (no placeholder text) before publish.
4. Update tests for new schema and validator behavior.
5. Re-run smoke and fail run if any new contract condition is violated.

Definition of done for this package:
1. Google template and `phase_v1.md` match exactly for Story/Sources addresses.
2. Tool calls in `artifacts/canonical_datasets/<run_id>_tool_calls.jsonl` show schema-consistent `sources_table` rows only.
3. No finalize failures from malformed sources/story anchor mismatch.
4. No placeholder strings in `sens_grid_values`.
5. Comps block includes target row + peers and populated control fields.

## TODO: Non-comps remediation from run `smoke_20260216T223755Z`
Scope note:
- This list intentionally excludes the comps issue, which is tracked separately.

1. Sensitivity writeback hardening
- Ensure `validation` always writes computed sensitivity grid results into `sens_grid_values` (and therefore `sens_grid_full`) after math execution.
- Add explicit post-write readback gate: fail phase if any placeholder token remains in `sens_grid_values`.
- Reference evidence:
  - `artifacts/run_logs/smoke_20260216T223755Z.log`
  - `artifacts/canonical_datasets/smoke_20260216T223755Z_tool_calls.jsonl`

2. Story citation contract enforcement
- Require `story_grid_citations` population with URL/source-tag/citation-id compliant entries before memo/publish completion.
- Add deterministic validator for citation cell format and row completeness tied to scenario rows.
- Reference evidence:
  - `artifacts/run_logs/smoke_20260216T223755Z.log`
  - `artifacts/canonical_datasets/smoke_20260216T223755Z_tool_calls.jsonl`

3. Publish/finalize status consistency
- Remove ability for publish phase to set `log_status=COMPLETED` before finalize validation passes.
- Enforce single source of truth:
  - publish uses `RUNNING`/`PENDING_FINALIZE`,
  - finalize writes terminal `COMPLETED` or `FAILED`.

4. Agent-log row schema discipline
- Enforce fixed-width schema per named table (`log_actions_table`, `log_assumptions_table`, `log_story_table`) with strict typing.
- Reject and auto-coerce invalid payloads (for example serial dates as integers in string columns) before append.
- Add unit tests that prevent mixed 3/4/5/6/8/11-column writes into the same log table.

5. Python math tool call compliance
- Security-only guardrail policy (approved):
  - allow imports in `python_execute_math`,
  - allow `print` and capture output streams,
  - keep hard runtime security controls (timeout, memory/process/file limits, output-size caps, isolated execution).
- Keep tool-call contract for deterministic structured outputs:
  - `def compute(inputs): ...`,
  - return structured JSON-compatible dict as the primary machine-readable result.
- Capture and return execution telemetry per call:
  - `stdout`,
  - `stderr`,
  - `exit_code`,
  - existing hash/timing metadata.
- Add prompt/skill examples that demonstrate import + print + structured return without disabling security controls.

6. Data-coverage quality gating
- Add explicit degraded-mode markers when transcript/corporate-action data is empty.
- Require either:
  - non-empty transcript/corporate-action signals, or
  - documented fallback rationale in `sources_table` and `log_assumptions_table`.

7. Canonical prefill quality normalization
- Add prefill consistency checks for dilution and share semantics (for example basic vs diluted anomalies and `incremental_shares_mm` logic).
- Add reconciliation rule when SEC and canonical revenue/EBIT differ materially:
  - store both values,
  - log variance reason,
  - mark selected source precedence.

8. Source quality bar upgrade
- Raise source-quality filters for IB-grade outputs:
  - prioritize SEC filings, company releases, primary transcripts, high-quality sell-side/financial press,
  - down-rank low-authority aggregators for core valuation assumptions.
- Add source-tier label in `sources_table` and require tier thresholds for critical assumptions.

## TODO: Post-smoke quality remediation from run `smoke_20260218T111741Z` (deferred)
Scope note:
- Story-grid linkage completeness (`Core narrative`, `Linked operating driver`, `KPI to track`) is handled in the current package and should not be deferred.
- Items below are the remaining critique backlog to implement later.

1. Provenance-safe intermediate math
- Remove hardcoded peer/fundamental constants in `python_execute_math` payloads.
- Require tool-fed structured inputs for comps and sensitivity math, with source tags per input block.
- Fail validation if math payload lacks required input provenance metadata.

2. Contradiction-check payload quality
- Normalize contradiction checker payload to compare metric values across sources/periods (not schema keys such as `period` vs `source`).
- Add typed contradiction schema tests to prevent semantic mismatch regressions.

3. Evidence quality in validation phase
- Tighten `fetch_news_evidence` handling so repeated empty result sets trigger explicit degraded-mode logging and fallback logic.
- Require minimum high-quality evidence rows for memo-critical claims before publish/finalize.

4. Sensitivity contract hardening
- Ensure `sens_base_value_ps`, `sens_wacc_vector`, and `sens_terminal_g_vector` are explicitly populated/validated alongside `sens_grid_values`.
- Block finalize if sensitivity vectors are null/blank even when grid values are present.

5. Status governance cleanup
- Prevent memo phase from writing terminal `log_status=COMPLETED`.
- Enforce terminal status writes only in finalize path.

6. Sources table quality normalization
- Replace placeholder literals such as `None` with normalized empty/explicit values.
- Standardize unit semantics and transform fields for SEC-scale values to avoid audit ambiguity.

7. Reconciliation transparency
- When canonical prefill values are later overwritten (for example SEC override), append a deterministic reconciliation row to `log_assumptions_table` with source precedence and variance.

8. Citation completion behavior
- Reduce finalize auto-backfill dependence by requiring LLM-native citation completion earlier in workflow.
- Keep finalize auto-backfill as last-resort safety net only, with explicit degraded-quality flag in logs.

### Approved Python math runtime policy (2026-02-17)
Decision:
1. `python_execute_math` will run with security guardrails only (no behavior-level bans on `import` or `print`).
2. Runtime must expose execution streams back to orchestration and logs (`stdout`, `stderr`, `exit_code`).
3. Sandbox/resource isolation remains mandatory to safely support broader Python syntax.

Implementation requirements:
1. Remove AST restrictions that block imports/prints while preserving dangerous-operation isolation at runtime boundary.
2. Execute in isolated subprocess/sandbox with bounded:
  - wall-clock timeout,
  - CPU and memory,
  - process count,
  - file output size.
3. Extend tool response schema for `python_execute_math`:
  - `output` (structured result from `compute(inputs)`),
  - `stdout`,
  - `stderr`,
  - `exit_code`.
4. Persist captured streams in run artifacts (`artifacts/canonical_datasets/<run_id>_tool_calls.jsonl`) for debugging and auditability.
5. Add tests covering:
  - import works,
  - print captured in `stdout`,
  - raised exceptions captured in `stderr`,
  - timeout/resource guards still enforce termination.

### Approved implementation package (2026-02-18)
Scope accepted:
1. Raise comps-note quality to IB standard:
- each row in `comps_table_full` `Notes` must include:
  - business model summary,
  - execution-quality commentary,
  - valuation multiple rationale (premium/discount reason vs target).
- enforce minimum detail threshold (multi-sentence, high-information notes).
2. Make table writes resilient and schema-safe:
- keep `sources_table` fixed 11-column schema (`B:L`) with deterministic type normalization.
- enforce fixed-width log table contracts:
  - `log_actions_table` = 9 columns,
  - `log_assumptions_table` = 10 columns,
  - `log_story_table` = 9 columns.
- prevent run-breaking `row_width` failures by deterministic row normalization before append/write.
3. Upgrade `python_execute_math` runtime:
- allow `numpy` usage (`import numpy as np`) for intermediate analytics.
- keep security/resource guardrails (timeout/memory/process/file/output limits, isolated subprocess).
- keep deterministic output contract (`compute(inputs)` returns JSON-compatible structured output).
4. Tool-call schema hardening:
- accept mixed primitive row cell types from model tool calls, then normalize in tool layer.
- reject malformed table payloads only after normalization and schema checks.
5. Finalize validation strengthening:
- treat descriptive comps headers (for example `Name`) as non-multiple columns when checking numeric coverage.
- enforce richer `comps_method_note` and row-note depth checks.

Execution alignment note:
1. No named-range renames are required for this package.
2. If any future template range changes are introduced, update in strict order:
- Google Sheets template,
- `phase_v1.md`,
- skills,
- tools/orchestrator validators/tests.

## Deliverables by end of V1
- Google Sheets run artifact with full valuation, scenario analysis, sensitivity, competitive context, and logs.
- Investment memo with thesis, scenario framing, weighted valuation conclusion, risks/catalysts, and citations.
- End-to-end multi-turn agent workflow using full mandatory tool stack.
- Finance skill pack with `SKILL.md`-style modular capabilities for repeatable quality.
- Final exported workbook artifact conforming to `Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx` structure.

## Implementation artifacts in repo
- Skill modules: `skills/`
- Skill implementation notes: `docs/architecture/v1-skill-pack-implementation-2026-02-15.md`
- Tool implementation notes: `docs/architecture/v1-tool-stack-implementation-2026-02-15.md`
- Orchestration implementation notes: `docs/architecture/v1-langgraph-orchestration-2026-02-15.md`

## What will make it reliable in practice:
- Complete orchestration wiring to use all 14 skills in the state-machine loop.
- Run full dry-runs (e.g., AAPL) and verify sheet + memo quality against the rubric.
- Add eval gates for citation coverage, contradiction resolution, and story-to-numbers coherence before publish.

## Reference docs reviewed
- Anthropic Agent Skills overview: https://docs.claude.com/en/docs/agents-and-tools/agent-skills
- Anthropic skill authoring best practices: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Anthropic skills in Claude Code (slash commands): https://docs.claude.com/en/docs/claude-code/slash-commands
- Anthropic skills with API: https://platform.claude.com/docs/en/build-with-claude/skills-guide
- Anthropic skills in SDK: https://docs.claude.com/en/api/agent-sdk/skills
- Anthropic engineering post: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Anthropic tool use overview: https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview
- Anthropic tool use implementation guide: https://docs.claude.com/en/docs/agents-and-tools/tool-use/implement-tool-use
- Anthropic code execution tool: https://docs.claude.com/en/docs/agents-and-tools/tool-use/code-execution-tool
- Anthropic bash tool: https://docs.claude.com/en/docs/agents-and-tools/tool-use/bash-tool
- Finnhub pricing: https://finnhub.io/pricing
- Finnhub API docs: https://finnhub.io/docs/api/
- Alpha Vantage docs: https://www.alphavantage.co/documentation/
- Alpha Vantage premium/free limits: https://www.alphavantage.co/premium/
- Tavily pricing: https://help.tavily.com/articles/8816424538-pricing
