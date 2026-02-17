---
name: sheets-dcf-executor
description: Execute the scenario DCF by writing inputs to Google Sheets, reading formula outputs from named ranges, and enforcing no off-sheet valuation math.
---

# Sheets DCF Executor

## Use this skill when

- Scenario assumptions are ready for model execution.
- You need trusted per-scenario and weighted outputs.

## Mandatory operating constraints

1. Use Google Sheets API for all writes/reads.
2. Never perform valuation arithmetic in code.
3. Never overwrite output ranges with constants.
4. Do not mutate local template files.

## Sheet targets

- Input ranges: scenario vectors and weights
- Output ranges:
  - `out_value_ps_pess`
  - `out_value_ps_base`
  - `out_value_ps_opt`
  - `out_value_ps_weighted`
  - `out_equity_value_weighted`
  - `out_enterprise_value_weighted`
- Diagnostics: `out_wacc`, `out_terminal_g`

## Workflow

1. Write finalized scenario assumptions and weights.
2. Trigger recalculation flow (if needed by engine behavior).
3. Read outputs only from named ranges.
4. Validate non-null outputs and invariant checks.
5. Log run status and output snapshot in `Agent Log`.

## Output contract

Return a valuation output bundle with:

- per-scenario value/share
- weighted value/share
- weighted equity and enterprise values
- key diagnostics
- check status

## Quality gates

1. Output values are read from `out_*` ranges only.
2. Checks pass or run is marked failed with explicit reason.
3. Output bundle includes range-level provenance.

## Required references

- `../finance-quality-bar-and-evidence/references/google-sheets-execution-policy.md`
- `../finance-quality-bar-and-evidence/references/sample-sheet-log-entries.md`
