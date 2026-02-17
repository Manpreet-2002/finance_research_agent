---
name: market-and-fundamentals-harvest
description: Ingest market, capital structure, and operating metrics from primary vendors, reconcile with filings, and write normalized inputs to the workbook.
---

# Market And Fundamentals Harvest

## Use this skill when

- Pulling current market snapshot and non-filing fundamentals.
- Reconciling capital structure fields with SEC values.

## Mandatory operating constraints

1. Finnhub is primary market/fundamentals vendor unless unavailable.
2. SEC remains primary for filing-accounting truth.
3. Use Google Sheets API only; no local template mutation.
4. No off-sheet valuation math.

## Required tool outputs

- Price, market cap, shares
- Cash/debt bridge fields
- Core operating metrics and estimate context (if available)

## Sheet targets

- `inp_px`, `inp_cash`, `inp_debt`, `inp_basic_shares`
- Reconciliation notes in `Agent Log`
- Source rows in `Sources`

## Workflow

1. Pull market snapshot and fundamentals from primary provider.
2. Normalize units and timestamps.
3. Reconcile shares/debt/cash with filing facts; log deltas.
4. Escalate to contradiction checker if thresholds are breached.
5. Write final inputs and provenance.

## Output contract

Return a normalized snapshot with:

- field
- value
- unit
- as-of timestamp
- provider endpoint
- reconciliation status

## Quality gates

1. Unit normalization and period labels are explicit.
2. Capital structure reconciliation is completed.
3. Any material mismatch has a logged decision.

## Required references

- `../finance-quality-bar-and-evidence/references/source-priority-and-contradiction-policy.md`
- `../finance-quality-bar-and-evidence/references/high-impact-thresholds-and-question-policy.md`
