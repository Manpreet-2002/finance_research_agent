---
name: memo-composer-ib-style
description: Compose an investment-banking-style memo using sheet-grounded scenario outputs, risk/catalyst framing, and citation-linked evidence.
---

# Memo Composer IB Style

## Use this skill when

- Valuation outputs and quality checks are complete.
- Final decision memo is required.

## Mandatory operating constraints

1. Headline numbers must come from workbook `out_*` ranges.
2. Non-trivial claims need citations.
3. Distinguish facts from judgment.
4. Avoid unsupported certainty language.
5. Use Google Sheets API when reading or writing workbook context.
6. Do not modify local template files in this repository.

## Required memo sections

1. Thesis summary
2. Scenario table (pess/base/opt + weights)
3. Weighted valuation conclusion
4. What must be true
5. Risks and catalysts
6. Competitive context
7. Citation appendix

## Workflow

1. Load outputs from `Output`, `Sensitivity`, `Comps`, `Story`, `Sources`.
2. Draft memo using weighted scenario framing.
3. Attach range mapping for each headline number.
4. Run citation and consistency audit before finalizing text.

## Output contract

Return memo draft plus a mapping table:

- claim
- sheet range
- source ID
- confidence label

## Quality gates

1. Memo passes quality rubric in shared references.
2. Numeric claims are range-mapped and source-backed.
3. Recommendation reflects scenario probabilities and sensitivity.

## Required references

- `../finance-quality-bar-and-evidence/references/sample-mini-memo.md`
- `../finance-quality-bar-and-evidence/references/quality-bar-and-standards.md`
