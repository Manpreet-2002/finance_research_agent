# DCF Skill - Template-first Google Sheets Engine + Research Logbook

**Template workbook:** `Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx`  
**Run logbook workbook:** `Valuation_Agent_Logbook_ExcelGraph.xlsx`

This skill defines the operational contract for a multi-turn valuation agent that starts from a semi pre-populated template and produces a high-quality, auditable valuation + story output.

---

## 0) Non-negotiable rules

1. Start each run by copying the template workbook.
2. Perform valuation math in Google Sheets formulas only.
3. Run a 3-part DCF:
- pessimistic
- neutral/base
- optimistic
4. Assign scenario probabilities/weights in-sheet.
5. Log assumption rationale, story rationale, and valuation rationale in-sheet.
6. Ask user for missing high-impact inputs when confidence is low.

---

## 1) Run lifecycle

### 1.1 Initialize run
- Copy template in Drive into run folder.
- Set run metadata:
  - `run_id`
  - `ticker`
  - `template_version`
  - `agent_version`
  - `start_ts`

### 1.2 Validate template contract
Before data writes, validate required tabs and named ranges exist.
If contract fails:
- mark run failed
- write failure reason in `Action_Ledger`
- stop run

### 1.3 Multi-turn loop
Loop until valuation quality gate passes:
1. gather/fix data
2. reason assumptions
3. write scenario inputs
4. read outputs
5. run checks
6. ask user for missing critical inputs if required

---

## 2) Spreadsheet contract

### 2.1 Input/write surfaces (named ranges)
Write only to approved `inp_*` and scenario ranges.

Minimum expected groups:
- identity and market:
  - `inp_ticker`, `inp_name`, `inp_px`
- base financials:
  - `inp_rev_ttm`, `inp_ebit_ttm`, `inp_tax_ttm`, `inp_da_ttm`, `inp_capex_ttm`, `inp_dNWC_ttm`
- balance/bridge:
  - `inp_cash`, `inp_debt`, `inp_other_adj`, `inp_basic_shares`
- discount-rate inputs:
  - `inp_rf`, `inp_erp`, `inp_beta`, `inp_kd`, `inp_dw`
- scenario assumptions:
  - `inp_pess_*`
  - `inp_base_*`
  - `inp_opt_*`
- scenario weights:
  - `inp_w_pess`, `inp_w_base`, `inp_w_opt`

### 2.2 Output/read surfaces
Read final values from `out_*` only.

Minimum outputs:
- per-scenario values:
  - `out_value_ps_pess`
  - `out_value_ps_base`
  - `out_value_ps_opt`
- weighted outputs:
  - `out_value_ps_weighted`
  - `out_equity_value_weighted`
- diagnostics:
  - `out_wacc_pess`, `out_wacc_base`, `out_wacc_opt`
  - `out_terminal_g_pess`, `out_terminal_g_base`, `out_terminal_g_opt`
  - `out_diluted_shares`

### 2.3 No hidden arithmetic policy
- Agent-side code may parse and compare values for validation.
- Agent-side code may not compute or override valuation outputs.
- Any reported headline valuation must come from `out_*` ranges.

---

## 3) Scenario design protocol

### 3.1 Required per-scenario assumptions
For each scenario define and log:
- revenue growth path
- operating margin path
- tax assumption
- reinvestment / capital intensity
- discount-rate inputs (or references to global assumptions)
- terminal growth

### 3.2 Scenario weighting protocol
- Set `inp_w_pess`, `inp_w_base`, `inp_w_opt` in sheet.
- Sum must equal 100% (or 1.0 if normalized convention).
- Weighted valuation must be formula-driven in workbook.

### 3.3 Narrative linkage protocol
For each scenario journal:
- business narrative tag
- key drivers
- what must be true
- key disconfirming evidence

---

## 4) Evidence and tooling protocol

### 4.1 Core tools
- SEC filings/XBRL tool
- Market/fundamentals tool (for example Finnhub)
- Web/news research tool
- Rates/macro tool (FRED/Treasury)

### 4.2 Optional but recommended tools
- earnings transcript ingestion
- corporate actions/splits history
- industry classification/peer discovery
- contradiction and source-quality checker

### 4.3 Evidence recording
Every material assumption must include:
- source type (`10-K`, `10-Q`, API vendor, company guidance, analyst judgment)
- source pointer (URL, accession id, endpoint)
- timestamp

---

## 5) In-sheet logging contract

### 5.1 Header metadata
Populate:
- `log_run_id`
- `log_status`
- `log_start_ts`
- `log_end_ts`
- `log_template_version`
- `log_agent_version`
- `log_model`
- `log_data_sources`
- `log_tokens`
- `log_cost_usd`

### 5.2 Action Ledger schema
Columns:
- `step`
- `ts_utc`
- `phase` (`intake`, `data`, `assumptions`, `model`, `checks`, `memo`, `publish`)
- `action` (`FETCH`, `WRITE`, `READ`, `VALIDATE`, `ASK_USER`, `PUBLISH`)
- `tool`
- `target`
- `summary`
- `citations`

### 5.3 Assumption Journal schema
Columns:
- `assumption_key`
- `scenario`
- `value_unit`
- `model_location`
- `source`
- `method`
- `rationale`
- `confidence`

### 5.4 Story Journal schema
Columns:
- `scenario`
- `story_claim`
- `linked_metric`
- `supporting_evidence`
- `risk_to_claim`

### 5.5 Central logbook append
Append one row per run into `Valuation_Agent_Logbook_ExcelGraph.xlsx` (`Runs` tab):
- run metadata
- weighted valuation headline
- confidence band
- sheet URL/id
- memo URL/id

---

## 6) Validation checks (must pass)

1. `WACC > g` in every scenario (hard fail)
2. scenario weights sum constraint (hard fail)
3. weighted output linkage check (hard fail)
4. EV bridge identity check within tolerance (hard fail)
5. diluted shares sanity (`diluted >= basic`, unless explicitly justified)
6. output completeness (no blank/NaN key outputs)
7. citation coverage for all major numeric claims in memo

Failure handling:
- set `log_status=FAILED`
- write explicit failure event in `Action_Ledger`
- return user-readable error and remediation prompt

---

## 7) Multi-turn user interaction policy

Ask user follow-up only when it materially impacts valuation quality, for example:
- missing high-impact assumptions with high uncertainty
- contradictory source data requiring preference choice
- mandate-specific preferences (conservative vs aggressive weighting)

Ask concise, decision-ready questions with default recommendation.

---

## 8) Memo generation contract

Memo must include:
- thesis summary
- scenario narratives (pess/base/opt)
- weighted valuation and implied return framing
- sensitivity highlights
- competitive positioning
- key risks/catalysts
- citation appendix linked to sheet values

Memo numbers must map to sheet output ranges, not model-side arithmetic.

---

## 9) Operational quick test

1. Copy template workbook.
2. Write sample ticker and core inputs.
3. Write scenario assumptions and weights.
4. Confirm per-scenario and weighted outputs populate.
5. Confirm logs append to `Action_Ledger` and `Assumption_Journal`.
6. Confirm one summary row appends to central logbook.

If all pass, workflow is ready for orchestrated runs.

---

## 10) Alignment summary
This runbook explicitly aligns to current target behavior:
- template-first start
- multi-turn reasoning
- 3-scenario DCF + weighting
- story-to-valuation linkage
- strict in-sheet math and auditability

