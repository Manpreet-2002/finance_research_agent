---
name: sec-filings-and-xbrl-extraction
description: Retrieve and normalize SEC filing and XBRL fundamentals, then write filing provenance while keeping orchestrator-owned core inputs deterministic.
---

# SEC Filings And XBRL Extraction

## Use this skill when

- You need filing-grounded fundamentals for model inputs.
- Vendor financial fields conflict or are incomplete.

## Mandatory operating constraints

1. SEC is primary for filing-accounting facts.
2. Use Google Sheets API only for writes/reads.
3. Do not modify local template files.
4. Do not compute final valuation outputs in code.

## Required sources

- SEC submissions and companyfacts endpoints
- Latest 10-K / 10-Q (and material 8-K where relevant)

## Sheet targets

- `Sources` tab citation rows with document IDs/timestamps
- `Agent Log` extraction activity rows
- Core `Inputs` ranges are orchestrator-owned; treat them as read-only evidence anchors in this phase.

## Workflow

1. Resolve ticker to CIK and identify most recent relevant filings.
2. Extract core facts with period and unit normalization.
3. Check unit consistency (USD, millions vs actual).
4. For taxes, map filing data to effective tax rate for `inp_tax_ttm` (decimal rate, not dollar tax expense).
5. If conflicts exist with vendor data, apply source priority policy.
6. Do not directly overwrite orchestrator-owned core inputs during this phase.
7. Write provenance to `Sources` including accession IDs and retrieval timestamps.
8. Log extraction method, caveats, and confidence.

## Output contract

Return normalized filing facts with:

- metric name
- value
- period end
- unit
- source document ID
- confidence

## Quality gates

1. Period alignment is explicit (TTM/FY labels).
2. Every written value has source metadata.
3. Conflicts are resolved and logged in `Checks`/`Agent Log`.

## Required references

- `../finance-quality-bar-and-evidence/references/source-priority-and-contradiction-policy.md`
- `../finance-quality-bar-and-evidence/references/quality-bar-and-standards.md`
