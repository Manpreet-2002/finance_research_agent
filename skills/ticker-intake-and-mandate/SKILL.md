---
name: ticker-intake-and-mandate
description: Capture ticker mandate, decision horizon, risk posture, and missing high-impact inputs for the valuation run, then initialize run metadata in Google Sheets.
---

# Ticker Intake And Mandate

## Use this skill when

- A new valuation run starts.
- User constraints and decision criteria are incomplete.
- High-impact assumptions must be clarified before model population.

## Mandatory operating constraints

1. Use Google Sheets API only for workbook operations.
2. Do not transform local template files in this repository.
3. Do not perform valuation math in code.

## Inputs to collect

1. `ticker` (required)
2. Mandate style (value, growth, quality, turnaround)
3. Horizon and risk tolerance
4. Known constraints (for example conservative terminal growth cap)
5. Any user-supplied assumptions

## Sheet writes

- `inp_ticker`, `inp_name`
- `log_run_id`, `log_status`, `log_start_ts`
- Initial `Action Ledger` rows at `log_actions_firstrow`

## Workflow

1. Validate ticker format and issuer identity.
2. Capture mandate and explicit success criteria.
3. Load `../finance-quality-bar-and-evidence/references/high-impact-thresholds-and-question-policy.md`.
4. Ask follow-up questions only for high-impact missing inputs.
5. Record accepted defaults and confidence level in `Agent Log`.
6. Produce a run brief for downstream skills.

## Output contract

Return a structured run brief containing:

- ticker and company name
- mandate summary
- missing high-impact inputs (if any)
- recommended defaults used
- constraints to enforce downstream

## Quality gates

1. No ambiguous mandate language remains.
2. High-impact uncertainties are either resolved or explicitly defaulted.
3. Intake assumptions are logged with rationale and confidence.
