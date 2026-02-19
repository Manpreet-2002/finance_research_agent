---
name: finance-quality-bar-and-evidence
description: Enforce the finance research quality bar, source hierarchy, contradiction handling, and memo grounding rules for the US-stocks valuation agent that writes to Google Sheets only.
---

# Finance Quality Bar And Evidence

Use this skill when a run needs strict quality control, source selection discipline, and investment-banking-style output standards.

## Non-negotiable rules

1. Use Google Sheets API for all workbook reads/writes.
2. Do not modify or transform the local template file `Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx`.
3. Keep valuation math in Google Sheets formulas only; code writes inputs and reads outputs.
4. Every material numeric claim must map to named ranges and source evidence.

## What to load from `references/`

- `references/quality-bar-and-standards.md`
  - Load first for scoring rubric and acceptance thresholds.
- `references/source-priority-and-contradiction-policy.md`
  - Load when sources disagree or confidence is low.
- `references/high-impact-thresholds-and-question-policy.md`
  - Load when deciding conservative defaults and confidence downgrades for high-impact uncertainty.
- `references/sector-assumption-playbook.md`
  - Load when setting sector-aware assumptions.
- `references/sample-mini-memo.md`
  - Load when composing or reviewing final memo quality.
- `references/sample-sheet-log-entries.md`
  - Load when writing `Agent Log` entries.

## Exit criteria

A run is high-quality only if:

1. Workbook checks pass and named-range outputs are complete.
2. Story, assumptions, and valuation remain internally consistent.
3. Citations and provenance are complete and contradiction checks are resolved.
4. Memo uses weighted scenario framing and maps all key numbers to sheet outputs.
