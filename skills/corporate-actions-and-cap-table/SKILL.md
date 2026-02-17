---
name: corporate-actions-and-cap-table
description: Retrieve corporate actions and cap-table relevant events, reconcile share and debt impacts, and update dilution and bridge assumptions in the workbook.
---

# Corporate Actions And Cap Table

## Use this skill when

- Share count, dilution, debt, or split history can affect valuation.
- Reconciling TSM and capital structure assumptions.

## Mandatory operating constraints

1. Alpha Vantage is primary for V1 corporate actions feed.
2. Reconcile with SEC disclosures for material events.
3. Write via Google Sheets API only.
4. No off-sheet math for diluted shares or valuation outputs.
5. Do not modify local template files in this repository.

## Sheet targets

- `Dilution (TSM)` and `Lease Capitalization`
- `inp_basic_shares`, `inp_debt`, `calc_diluted_shares`, `calc_lease_debt`
- Source and action log entries

## Workflow

1. Pull splits/dividends/buyback events and relevant debt events.
2. Align event timing with modeling period.
3. Reconcile reported share count impacts vs current assumptions.
4. If discrepancy is material, run contradiction policy and log decision.
5. Update cap-table inputs and document rationale.

## Output contract

Return normalized action events with:

- action type
- effective date
- magnitude
- modeled implication
- source endpoint and timestamp

## Quality gates

1. Diluted share path is internally consistent.
2. Split-adjustments are correctly reflected in share assumptions.
3. Material cap-table assumptions are evidence-backed.

## Required references

- `../finance-quality-bar-and-evidence/references/source-priority-and-contradiction-policy.md`
- `../finance-quality-bar-and-evidence/references/high-impact-thresholds-and-question-policy.md`
