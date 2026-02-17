---
name: sensitivity-engine
description: Populate and interpret valuation sensitivities and stress cases in the workbook to quantify fragility and scenario asymmetry.
---

# Sensitivity Engine

## Use this skill when

- Base valuation outputs are available.
- You need robustness checks for key assumptions.

## Mandatory operating constraints

1. Build sensitivity math in workbook formulas only.
2. Use Google Sheets API for all sensitivity updates.
3. Do not compute sensitivity tables in code.
4. Do not modify local template files in this repository.

## Sheet targets

- `Sensitivity` tab grids/charts
- `Checks` flags for fragility and nonlinear behavior
- `Agent Log` interpretation notes

## Workflow

1. Define stress axes (typically WACC x terminal growth, margin x growth).
2. Populate sheet sensitivity inputs/formula references.
3. Read resulting grid outputs from sheet ranges.
4. Identify nonlinear cliffs and threshold behavior.
5. Write concise interpretation for memo consumption.
6. Ensure `sens_grid_values` contains numeric values only; placeholder strings are a hard failure.

## Output contract

Return sensitivity summary with:

- tested ranges
- downside/upside sensitivity percentages
- fragility flags
- implications for conviction and position sizing

## Quality gates

1. Stress grid links to active scenario assumptions.
2. Interpretation references concrete grid cells/ranges.
3. Risks are escalated when small input shifts cause large output changes.
4. `sens_grid_values` has no placeholder tokens (for example `populate via agent scenario sweep`).

## Required references

- `../finance-quality-bar-and-evidence/references/high-impact-thresholds-and-question-policy.md`
- `../finance-quality-bar-and-evidence/references/quality-bar-and-standards.md`
