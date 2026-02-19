---
name: assumption-engine-pess-base-opt
description: Build pessimistic, base, and optimistic assumption vectors with explicit probabilities, evidence-backed rationale, and sector-aware adaptation before DCF execution.
---

# Assumption Engine Pess Base Opt

## Use this skill when

- Converting evidence into scenario inputs and weights.
- Preparing the workbook for DCF execution.

## Mandatory operating constraints

1. Assumptions must be reasoned from evidence, not generic defaults.
2. Sector and industry adjustments are allowed in the run sheet copy.
3. Do not alter local template files in repo.
4. Use Google Sheets API for all workbook reads/writes.
5. All valuation math remains in Google Sheets formulas.

## Required inputs

- Filing-backed fundamentals
- Market/capital structure snapshot
- Rates/macro context
- Transcript and peer insights

## Sheet targets

- `inp_pess_*`, `inp_base_*`, `inp_opt_*`
- `inp_w_pess`, `inp_w_base`, `inp_w_opt`
- Assumption rationale rows in `Agent Log`

## Workflow

1. Load sector anchors from playbook, then adjust for company specifics.
2. Define per-scenario paths for growth, margin, tax, reinvestment, WACC, terminal growth.
3. Set scenario weights based on probability, asymmetry, and evidence strength.
4. Run preflight checks (`WACC > g`, weight sum, internal consistency).
5. If uncertainty exceeds high-impact thresholds, apply conservative defaults, widen scenario spreads, and log confidence impacts.
6. Write assumptions and rationale with confidence labels.

## Output contract

Return scenario package containing:

- all key assumption vectors
- scenario weights
- rationale text
- key disconfirming evidence
- confidence by scenario

## Quality gates

1. Every major assumption has cited evidence and rationale.
2. Scenario weights are justified and sum correctly.
3. Story and assumptions are linked before model execution.

## Required references

- `../finance-quality-bar-and-evidence/references/sector-assumption-playbook.md`
- `../finance-quality-bar-and-evidence/references/high-impact-thresholds-and-question-policy.md`
- `../finance-quality-bar-and-evidence/references/quality-bar-and-standards.md`
