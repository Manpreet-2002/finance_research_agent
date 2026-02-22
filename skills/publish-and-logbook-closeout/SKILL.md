---
name: publish-and-logbook-closeout
description: Perform final publish checks, set run completion status, and close the in-sheet logbook with artifact references and summary diagnostics.
---

# Publish And Logbook Closeout

## Use this skill when

- All model and memo quality gates have passed.
- Final run status must be set and artifacts closed out.

## Mandatory operating constraints

1. Run only after citation and consistency audit passes.
2. `log_status` and `log_end_ts` are orchestration-managed guardrails; do not write them from LLM tool calls.
3. Do not publish if hard checks fail.
4. Keep final valuation numbers sourced from existing output ranges.
5. Do not modify local template files in this repository.

## Sheet targets

- `log_status`, `log_end_ts`
- `Agent Log` final action rows
- `Output` publish metadata fields (if configured)

## Workflow

1. Confirm checks, citations, and memo readiness are all green.
2. Append final summary rationale rows to `Agent Log` tables if needed.
3. Persist artifact IDs/links.
4. Report publish readiness and residual risks.

## Output contract

Return closeout summary with:

- run status
- final valuation headline ranges
- artifact references
- any residual risks

## Quality gates

1. No unresolved high-severity issues.
2. All required logbook sections are populated.
3. Publish status reflects actual gate outcomes.

## Required references

- `../finance-quality-bar-and-evidence/references/sample-sheet-log-entries.md`
- `../finance-quality-bar-and-evidence/references/quality-bar-and-standards.md`
