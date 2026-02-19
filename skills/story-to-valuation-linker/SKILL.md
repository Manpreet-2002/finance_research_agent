---
name: story-to-valuation-linker
description: Enforce Damodaran-style story-to-numbers consistency by mapping narrative claims to assumptions, outputs, and disconfirming evidence.
---

# Story To Valuation Linker

## Use this skill when

- Narrative is being prepared for memo output.
- Story claims need explicit mapping to model assumptions.

## Mandatory operating constraints

1. Every major story claim must map to model levers or outputs.
2. Every claim needs supporting and disconfirming evidence.
3. Write story mapping inside workbook tabs via Google Sheets API.
4. Do not modify local template files in this repository.

## Sheet targets

- `Story` tab claim-to-metric mapping
- `Agent Log` story rationale rows
- `Sources` link references

Story anchor map (must follow):
1. `story_thesis` => `Story!B5`
2. `story_growth` => `Story!B8`
3. `story_profitability` => `Story!B11`
4. `story_reinvestment` => `Story!B14`
5. `story_risk` => `Story!B17`
6. `story_sanity_checks` => `Story!B20`
7. `story_core_narrative_rows` => `Story!C24:C26` (pess/base/opt rows)
8. `story_linked_operating_driver_rows` => `Story!D24:D26`
9. `story_kpi_to_track_rows` => `Story!E24:E26`

## Workflow

1. Enumerate thesis claims and risk/catalyst claims.
2. Map each claim to specific `inp_*` or `out_*` ranges.
3. Add "what must be true" conditions and failure signals.
4. Add disconfirming evidence per scenario.
5. Populate scenario-grid operating linkage fields for each scenario row:
- `story_core_narrative_rows`
- `story_linked_operating_driver_rows`
- `story_kpi_to_track_rows`
6. Verify no claim remains unlinked to sheet data.
7. Populate `story_grid_citations` with explicit URL or `citation_id` tokens for each scenario row.

## Output contract

Return story-link map with:

- claim text
- linked ranges
- supporting evidence IDs
- disconfirming evidence IDs
- confidence

## Quality gates

1. No free-floating narrative claims.
2. Claim mapping survives contradiction audit.
3. Risk statements are concrete and monitorable.
4. No story text is written into legacy right-side blocks (`Story!C:G`) for thesis/growth/profitability/reinvestment/risk/sanity fields.
5. Do not leave `Core narrative`, `Linked operating driver`, or `KPI to track` blank for any scenario row.

## Required references

- `../finance-quality-bar-and-evidence/references/quality-bar-and-standards.md`
- `../finance-quality-bar-and-evidence/references/sample-sheet-log-entries.md`
