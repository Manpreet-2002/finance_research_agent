# Workbook Range Contract (Named-Range Only)

Use this contract to generate named-range keys and named-table targets.

## Valid tab names (exact)

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

## Named-range families

1. Inputs and assumptions: `inp_*`
2. Calculated helper ranges: `calc_*` (read-only)
3. Outputs: `out_*` (read-only)
4. Run/log metadata: `log_*`
5. Dynamic comps/table anchors: `comps_*`, `sources_*`

## Dynamic comps contract

1. `comps_header`
2. `comps_firstrow`
3. `comps_table`
4. `comps_table_full`
5. `comps_peer_tickers`
6. `comps_peer_names`
7. `comps_multiples_header`
8. `comps_multiples_values`
9. `comps_method_note`
10. `comps_peer_count`
11. `comps_multiple_count`

Comps write rules:
1. Use `sheets_write_named_table` with `table_name=comps_table_full`.
2. Header must start with `Ticker` and end with `Notes`.
3. First data row must be the target ticker.
4. `comps_peer_count` includes target row.

## Named table anchors

1. `sources_table`
2. `log_actions_table`
3. `log_assumptions_table`
4. `log_story_table`

## Story linkage contract

1. Narrative anchors:
- `story_thesis`
- `story_growth`
- `story_profitability`
- `story_reinvestment`
- `story_risk`
- `story_sanity_checks`
2. Scenario grid anchors:
- `story_grid_header`
- `story_grid_rows`
- `story_grid_citations`
3. Required scenario-linkage columns:
- `story_core_narrative_rows`
- `story_linked_operating_driver_rows`
- `story_kpi_to_track_rows`
4. `story_memo_hooks` must contain claim-to-range hook rows for memo assembly.

Log table widths:
1. `log_actions_table` => 9 columns
2. `log_assumptions_table` => 10 columns
3. `log_story_table` => 9 columns

## Tool contract

1. Allowed LLM sheet tools:
- `sheets_write_named_ranges`
- `sheets_read_named_ranges`
- `sheets_write_named_table`
- `sheets_append_named_table_rows`
- `sheets_read_outputs`
2. Named-table payload shape:
- `rows` must be a rectangular 2D array.
- Every table cell is a scalar string in tool payloads (including numeric/date/formula literals).

3. Disallowed for LLM runtime:
- `sheets_write_ranges`
- `sheets_read_ranges`
- Any A1 payload (`Tab!A1`, `A1:B10`)

## Valid vs invalid examples

1. Valid named read/write: `inp_ticker`, `inp_base_wacc`, `log_status`, `comps_multiples_header`
2. Valid named table target: `comps_table_full`, `sources_table`, `log_actions_table`
3. Invalid: `Inputs!C20`, `'Agent Log'!B17:J17`, `Sources_A1`, `Inputs!inp_ticker`
4. Invalid table payload: `rows=[[\"AAPL\", {\"ev_sales\": 7.2}]]` (object cell)
