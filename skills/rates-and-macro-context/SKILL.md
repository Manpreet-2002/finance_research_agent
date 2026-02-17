---
name: rates-and-macro-context
description: Build discount-rate and macro regime context from FRED/Treasury series and write rate assumptions with provenance into the valuation workbook.
---

# Rates And Macro Context

## Use this skill when

- Setting risk-free rate and macro regime context.
- Validating cost-of-capital assumptions for scenario design.

## Mandatory operating constraints

1. FRED/Treasury is primary for rates and macro series.
2. Use Google Sheets API only for writes.
3. Keep valuation math in sheet formulas.
4. Do not modify local template files in this repository.

## Sheet targets

- `inp_rf`, `inp_erp`, `inp_beta` (where applicable)
- Context notes in `Sources` and `Agent Log`

## Workflow

1. Pull latest risk-free series (`DGS10` and relevant tenor context).
2. Capture macro regime signals relevant to discount rates.
3. Set rate assumptions with explicit as-of dates.
4. Validate consistency with scenario `WACC > g` requirements.
5. Log assumptions and evidence references.

## Output contract

Return a rates snapshot with:

- series ID
- value
- observation date
- unit
- rationale for how it informs `inp_rf` and WACC assumptions

## Quality gates

1. Rate assumptions are timestamped and source-backed.
2. Macro commentary is concise and valuation-relevant.
3. Discount-rate inputs are coherent with scenario assumptions.

## Required references

- `../finance-quality-bar-and-evidence/references/quality-bar-and-standards.md`
- `../finance-quality-bar-and-evidence/references/high-impact-thresholds-and-question-policy.md`
