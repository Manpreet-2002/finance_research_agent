---
name: sec-filings-and-xbrl-extraction
description: Retrieve and normalize SEC filing and XBRL fundamentals, then write source-backed accounting inputs and provenance to the valuation workbook.
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

- `Inputs` tab ranges for filing-grounded fundamentals (`inp_rev_ttm`, `inp_ebit_ttm`, `inp_tax_ttm`, etc.)
- `Sources` tab citation rows with document IDs/timestamps
- `Agent Log` extraction activity rows

## Workflow

1. Resolve ticker to CIK and identify most recent relevant filings.
2. Extract core facts with period and unit normalization.
3. Check unit consistency (USD, millions vs actual).
4. If conflicts exist with vendor data, apply source priority policy.
5. Write normalized values to approved input ranges.
6. Write provenance to `Sources` including accession IDs and retrieval timestamps.
7. Log extraction method, caveats, and confidence.

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
