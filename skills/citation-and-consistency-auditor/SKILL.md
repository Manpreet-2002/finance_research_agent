---
name: citation-and-consistency-auditor
description: Audit numeric grounding, citation completeness, and cross-source consistency before memo publication.
---

# Citation And Consistency Auditor

## Use this skill when

- Preparing final validation before memo release.
- Any contradiction or missing provenance is suspected.

## Mandatory operating constraints

1. Every material numeric claim must map to a sheet range and source.
2. Source conflicts must follow priority policy and be logged.
3. Failing checks block publish.
4. Use Google Sheets API for all workbook reads/writes.
5. Do not modify local template files in this repository.

## Sheet targets

- `Sources` completeness checks
- `Checks` contradiction and invariant rows
- `Agent Log` audit results

## Workflow

1. Build claim inventory from story/memo draft.
2. Map each claim to `out_*`/`inp_*` ranges and source IDs.
3. Run contradiction checks across SEC, vendors, and web evidence.
4. Mark unresolved conflicts and valuation impact.
5. Fail run if critical claims lack valid citations.
6. Verify `sources_table` rows follow fixed 11-column schema:
- `field_block`, `source_type`, `dataset_doc`, `url`, `as_of_date`, `notes`, `metric`, `value`, `unit`, `transform`, `citation_id`.
- reject mixed column orders across rows.

## Output contract

Return audit report with:

- missing citation list
- contradiction list with severity
- pass/fail status
- remediation actions

## Quality gates

1. 100% coverage for headline numeric claims.
2. No unresolved high-severity contradictions.
3. Audit trail is logged in sheet.
4. Every story grid citation resolves to either a valid URL or a `citation_id` present in `sources_table`.

## Required references

- `../finance-quality-bar-and-evidence/references/source-priority-and-contradiction-policy.md`
- `../finance-quality-bar-and-evidence/references/quality-bar-and-standards.md`
