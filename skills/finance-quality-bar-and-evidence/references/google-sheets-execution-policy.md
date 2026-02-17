# Google Sheets Execution Policy

## Required execution model

1. Copy the canonical template into a run-specific Google Sheet artifact.
2. Read/write using Google Sheets API only.
3. Do not alter the local template workbook file in repository.
4. Keep valuation computation in workbook formulas.

## Allowed agent behavior

1. Write inputs to approved `inp_*` and scenario ranges.
2. Read outputs from `out_*` named ranges.
3. Append logs to `Agent Log` and source records to `Sources`.
4. Add sector-specific helper rows/charts/comments in the run copy when needed.

## Disallowed agent behavior

1. Computing final valuation outputs in code.
2. Overwriting output cells with hardcoded values.
3. Mutating local `.xlsx` template files in repo.

## Verification

1. For each headline number in memo, store range mapping.
2. Confirm weighted valuation is formula-linked in sheet.
3. Confirm no code path returns valuation if output ranges are blank.
