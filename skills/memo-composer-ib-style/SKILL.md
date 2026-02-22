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
2. Populate Story scenario-linkage fields before final memo completion:
- `story_core_narrative_rows` (`Story!C24:C26`)
- `story_linked_operating_driver_rows` (`Story!D24:D26`)
- `story_kpi_to_track_rows` (`Story!E24:E26`)
- `story_memo_hooks` (`Story!C28:G30`) with 5 columns:
- `claim_title` (resolved values; no raw range IDs)
- `linked_ranges_csv` (comma-separated named-range IDs)
- `memo_detail` (resolved value narrative)
- `confidence` (`High`/`Medium`/`Low`)
- `citation_token`
3. Draft memo using weighted scenario framing.
4. Attach range mapping for each headline number.
5. Run citation and consistency audit before finalizing text.

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
4. Story grid has non-empty `Core narrative`, `Linked operating driver`, and `KPI to track` for pess/base/opt rows.

## Required references

- `../finance-quality-bar-and-evidence/references/sample-mini-memo.md`
- `../finance-quality-bar-and-evidence/references/quality-bar-and-standards.md`
