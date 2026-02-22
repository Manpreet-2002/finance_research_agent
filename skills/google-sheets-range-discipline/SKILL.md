---
name: google-sheets-range-discipline
description: Enforce named-range-only Google Sheets operations for valuation runs, including named-table writes/appends and strict contract validation.
---

# Google Sheets Range Discipline

## Use this skill when

- You call any Google Sheets tool.
- You read or write workbook data in any phase.
- You build comps/sources/log tables.

## Mandatory operating constraints

1. Use Google Sheets API tools only.
2. Never modify local workbook files in repository.
3. Use named ranges only for LLM runtime operations.
4. Do not use A1 notation (`Tab!A1`, `A1:B10`) in tool payloads.
5. Keep valuation math in sheet formulas, not code.

## Canonical tab whitelist (exact spellings)

1. `README`
2. `Inputs`
3. `Dilution (TSM)`
4. `R&D Capitalization`
5. `Lease Capitalization`
6. `DCF`
7. `Sensitivity`
8. `Comps`
9. `Checks`
10. `Sources`
11. `Story`
12. `Output`
13. `Agent Log`

## Core named-range whitelist

1. Intake/log: `inp_ticker`, `inp_name`, `log_run_id`, `log_status`, `log_start_ts`, `log_end_ts`
2. Market/rates: `inp_px`, `inp_rf`, `inp_erp`, `inp_beta`
3. Capital structure: `inp_cash`, `inp_debt`, `inp_basic_shares`, `calc_diluted_shares`, `calc_lease_debt`
4. Scenario weights: `inp_w_pess`, `inp_w_base`, `inp_w_opt`
5. Scenario blocks: `inp_pess_*`, `inp_base_*`, `inp_opt_*`
6. Outputs: `out_value_ps_pess`, `out_value_ps_base`, `out_value_ps_opt`, `out_value_ps_weighted`, `out_equity_value_weighted`, `out_enterprise_value_weighted`, `OUT_WACC`, `out_terminal_g`
7. Comps dynamic contract: `comps_header`, `comps_firstrow`, `comps_table`, `comps_table_full`, `comps_peer_tickers`, `comps_peer_names`, `comps_multiples_header`, `comps_multiples_values`, `comps_method_note`, `comps_peer_count`, `comps_multiple_count`
8. Table anchors: `sources_table`, `log_actions_table`, `log_assumptions_table`, `log_story_table`
9. Tax input semantics: `inp_tax_ttm` is an effective tax rate (decimal), never dollar tax expense.

## Comps table layout contract (must follow)

1. Comps must be written as one rectangular table to `comps_table_full`.
2. Header row (`Comps!B7` anchor via named range):
- first non-empty header cell = `Ticker`
- last non-empty header cell = `Notes`
- middle headers = industry-specific metric names
3. First data row (`Comps!B8` anchor via named range) must be the run target ticker (`inp_ticker`).
4. Comps values must be consecutive between `Ticker` and `Notes` columns (no interior blank columns).
5. Do not append into comps using `sheets_append_named_table_rows`; use `sheets_write_named_table` for full overwrite.
6. `comps_peer_count` and `comps_multiple_count` are derived from `comps_table_full`; do not write them directly.

## Story layout contract (must follow)

1. Story narrative inputs are down-column single-cell anchors:
- `story_thesis` => `Story!B5`
- `story_growth` => `Story!B8`
- `story_profitability` => `Story!B11`
- `story_reinvestment` => `Story!B14`
- `story_risk` => `Story!B17`
- `story_sanity_checks` => `Story!B20`
2. Do not write narrative text into legacy right-side blocks (`C:G`) for these fields.
3. `story_grid_rows`, `story_grid_header`, and `story_grid_citations` remain table-style ranges and must be populated separately.
4. `story_grid_header` is template-owned/read-only. Do not write it during runtime.
5. Required scenario linkage columns:
- `story_core_narrative_rows` => `Story!C24:C26`
- `story_linked_operating_driver_rows` => `Story!D24:D26`
- `story_kpi_to_track_rows` => `Story!E24:E26`
6. Do not leave any scenario row blank for the three linkage columns above.
7. Preserve scenario labels in `story_grid_rows` column 1 as exactly `Pessimistic`, `Neutral`, `Optimistic`.
8. `story_memo_hooks` is a fixed 3x5 block (`Story!C28:G30`) with row schema:
- `claim_title` (resolved values, no raw range IDs)
- `linked_ranges_csv` (comma-separated named-range IDs)
- `memo_detail` (resolved value narrative)
- `confidence` (`High`/`Medium`/`Low`)
- `citation_token`

## Sensitivity layout contract (must follow)

1. `sens_wacc_vector` is vertical (`5x1`).
2. `sens_terminal_g_vector` is horizontal (`1x5`).
3. `sens_grid_values` is `5x5`.
4. If you provide vector payloads, orientation must match named-range geometry exactly.

## Sources schema contract (must follow)

`sources_table` uses fixed 11-column schema in `B:L`:
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

Every non-empty source row must:
1. include all 11 columns in order.
2. use an absolute URL in `url` (`https://...`).
3. provide a stable `citation_id` that can be referenced from Story/Log rows.
4. avoid mixed schemas across rows.
5. do not include the header row in `rows`; pass data rows only.

## Agent Log schema contract (must follow)

Named log tables are fixed-width:
1. `log_actions_table`: 9 columns
2. `log_assumptions_table`: 10 columns
3. `log_story_table`: 9 columns

Minimum required columns for each appended row:
1. column 1: timestamp/phase marker
2. column 2: category/action type
3. column 3: substantive message

Do not append 11-column source-style rows into `log_*_table`.

## Tool-specific rules

1. `sheets_write_named_ranges`
- Keys must be existing named ranges only.
- Never write formula-owned ranges (`out_*`, `calc_*`).
- Never write runtime read-only ranges (`story_grid_header`, `log_status`, `log_end_ts`).

2. `sheets_read_named_ranges`
- `names` must be existing named ranges only.
- Never pass A1 strings or mixed forms like `Inputs!inp_ticker`.

3. `sheets_write_named_table`
- `table_name` must reference a named table block (for example `comps_table`, `sources_table`, `log_actions_table`).
- `rows` must be a rectangular 2D array (`[[cell_1, cell_2, ...], ...]`).
- Every cell in `rows` must be a scalar string value (numbers, dates, and formulas are passed as strings).
- Rows must match table width contract.
- For comps, use `table_name=comps_table_full` and include header + all data rows in one write.

4. `sheets_append_named_table_rows`
- `table_name` must be a named table block.
- Appends use first-empty-row policy inside the table bounds.
- `rows` payload format is identical to `sheets_write_named_table`: rectangular 2D array of scalar string cells.
- For `sources_table`, append rows only in the fixed 11-column schema above.
- Do not use this tool for `comps_table` or `comps_table_full`.

## Anti-patterns (never repeat)

1. `sheets_write_ranges` / `sheets_read_ranges` payloads in LLM runtime.
2. A1 strings (`Sources!A2:F20`, `'Agent Log'!B17:J17`).
3. Fabricated names that are not in template named ranges.
4. Writes to `out_*` or `calc_*`.

## Output contract

When proposing a sheets tool call, internally keep this tuple consistent:

- `tool`: one of named-range/named-table tools
- `validated_targets`: exact named ranges checked against contract
- `purpose`: why this read/write is needed

## Quality gates

1. Zero invalid-range errors.
2. Zero A1 notation in LLM sheet tool payloads.
3. Every named target exists in template contract.
4. Table writes use named table ranges only.

## Required reference

- `references/workbook-range-contract.md`
