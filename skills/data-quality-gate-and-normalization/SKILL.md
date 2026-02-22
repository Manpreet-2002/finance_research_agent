---
name: data-quality-gate-and-normalization
description: Run deterministic pre-model data quality checks on canonical inputs, source consistency, and contradiction flags before scenario assumptions are written.
---

# Data Quality Gate And Normalization

## Use this skill when

- Entering `data_quality_checks` phase.
- Validating whether assumptions can proceed.
- Preventing bad inputs from contaminating DCF/comps/story.

## Mandatory operating constraints

1. Use Google Sheets named-range tools only.
2. Never use A1 notation or arbitrary row/column access.
3. Do not write formula-owned ranges (`out_*`, `calc_*`).
4. Keep final valuation math in Google Sheets formulas.
5. Core inputs (`inp_rev_ttm`, `inp_ebit_ttm`, `inp_tax_ttm`, `inp_cash`, `inp_debt`, `inp_basic_shares`, `inp_px`, `inp_rf`, `inp_erp`, `inp_beta`) are orchestrator-owned baselines in this phase; only orchestrator repair logic may overwrite them.
6. Record every material remediation in `log_actions_table` or `log_assumptions_table`.

## Required checks

1. Core input completeness
- Validate `inp_rev_ttm`, `inp_ebit_ttm`, `inp_tax_ttm`, `inp_px`, `inp_rf`, `inp_erp`, `inp_beta`, `inp_cash`, `inp_debt`, `inp_basic_shares`.
- Missing/invalid numeric fields are blocking issues.
- Baseline drift versus orchestrator-reconciled canonical inputs is a blocking issue.

2. Unit/range sanity
- Tax rates must be in a realistic band.
- `inp_tax_ttm` is an effective tax **rate** only (decimal). Valid forms: `0.19` or `19%`.
- Never write absolute tax expense dollars into `inp_tax_ttm`.
- Price and shares must be positive.
- Rates and beta must be plausible for a public US equity.

3. Source consistency
- Read `sources_table` and ensure material inputs have source traceability.
- If contradictions are detected, call `check_source_contradictions` and log the resolution rule.

4. Checks discipline
- Read `checks_statuses` and identify failing checks before assumptions phase starts.
- If checks fail due to missing data, record explicit remediation actions.

## Output contract

Produce a concise quality packet with:

- blocking issues (must-fix)
- non-blocking warnings
- normalization actions applied
- residual risk and confidence impact

## Quality bar

1. No silent missing critical inputs.
2. No unresolved high-severity contradictions.
3. Every correction mapped to named ranges and logged.
4. Assumptions phase starts only when data quality gate is satisfied.

## Required references

- `../finance-quality-bar-and-evidence/references/quality-bar-and-standards.md`
- `../finance-quality-bar-and-evidence/references/source-priority-and-contradiction-policy.md`
