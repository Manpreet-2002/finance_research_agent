# US Stocks Finance Research Agent Platform (2026)
## PRD + System Design (Template-first Google Sheets engine)

> One-liner: Enter a US ticker -> generate a top-quality Google Sheets valuation workbook and a high-quality investment memo, with full assumption/story auditability logged inside the sheet.

---

## 1) Product intent

### 1.1 Core objective
Build a multi-turn finance research agent that starts from a semi pre-populated Google Sheets template, gathers and validates evidence, reasons through assumptions, performs scenario-based DCF in Sheets, and delivers:
- a professional valuation workbook (with transparent assumptions, scenarios, sensitivities, and competitive analysis), and
- a professional investment memo that ties valuation outputs to business narrative (Damodaran-style story-to-numbers coherence).

### 1.2 Hard requirements
- Spreadsheet template is the starting point (copy from canonical data-service template each run).
- Agent must run a 3-part DCF:
  - pessimistic
  - neutral/base
  - optimistic
- Agent must decide scenario assumptions and scenario probabilities/weights.
- Agent must write rationale for assumptions, story, and valuation in-sheet.
- Agent must ask user for missing or high-impact data when needed.
- Agent must not perform math transformations outside Google Sheets formulas.
- Agent can write formulas, read outputs, and iterate assumptions across turns.

### 1.3 Quality bar
Think like a top investment banker:
- broad evidence collection (filings, fundamentals, guidance, macro, peers, catalysts)
- clear assumptions linked to evidence
- valuation sensitivity and downside framing
- competitive context and market structure analysis
- internally consistent narrative and model outputs

### 1.4 Implementation references (repo-local)
- Tool stack implementation: `docs/architecture/v1-tool-stack-implementation-2026-02-15.md`
- Skill pack implementation: `docs/architecture/v1-skill-pack-implementation-2026-02-15.md`
- Orchestration implementation: `docs/architecture/v1-langgraph-orchestration-2026-02-15.md`
- Phase plan and scope: `phase_v1.md`

---

## 2) Design principles from latest OpenAI + Anthropic agent guidance

### 2.1 Agent safety and control
- Use strict structured tool contracts (JSON schema, minimal free-form).
- Keep untrusted data out of privileged instruction channels.
- Apply least-privilege tool permissions and explicit approvals for write/destructive operations.
- Restrict high-risk tool actions (sheet mutations, external posting, file writes) through policy gates.

### 2.2 Reliability
- Use deterministic workflow phases with typed intermediate artifacts.
- Require citations on factual and numeric claims.
- Separate reasoning decisions from numerical computation:
  - reasoning in model
  - math in spreadsheet formulas only

### 2.3 Observability and improvement
- Capture full run traces (plan, tool calls, outputs, assumption changes).
- Run trace graders and evals for regressions.
- Track failure classes (wrong tool, stale data, assumption drift, missing citations, template contract break).

---

## 3) Scope

### 3.1 In scope (V1)
- US listed equities (single ticker per run).
- Google Sheets as remote compute and audit artifact.
- Multi-turn chat workflow with clarifying questions.
- 3-scenario DCF with weighted expected value.
- Sensitivity analysis and competitive analysis.
- Memo generation with citations and explicit scenario framing.

### 3.2 Out of scope (V1)
- Intraday trading and execution.
- Derivatives/options pricing.
- Portfolio optimization across many tickers.

---

## 4) User inputs and outputs

### 4.1 Input contract
Required:
- `ticker`

Optional:
- mandate style (value, growth, quality, turnaround)
- horizon
- user-provided assumptions
- explicit constraints (for example conservative terminal growth cap)

### 4.2 Output contract
- Google Sheet run artifact (template copy) containing:
  - Inputs and assumption logs
  - historical and forward operating data
  - 3-scenario DCF + weighted valuation
  - sensitivity tables/charts
  - competitive analysis tables
  - story/risk register
  - run logbook
- Investment memo (markdown/doc/pdf) with:
  - thesis
  - scenario narrative
  - weighted valuation conclusion
  - key risks and catalysts
  - citations

---

## 5) Template-first Sheets architecture

### 5.1 Run initialization
1. Copy semi pre-populated template from data-service canonical template.
2. Register run metadata (`run_id`, `template_version`, `ticker`, timestamps).
3. Validate required named ranges/tabs exist.

### 5.2 Spreadsheet-as-calculator policy
- Agent writes inputs and formulas with `USER_ENTERED`.
- Agent reads computed outputs from named output ranges.
- Agent never computes final valuation arithmetic in model-side code.
- Any derived numeric value shown to users/memo must be read from Sheets outputs.

### 5.3 Suggested tab contract
- `Inputs`
- `Historicals`
- `Assumptions`
- `Scenario_Pessimistic`
- `Scenario_Neutral`
- `Scenario_Optimistic`
- `Scenario_Weights`
- `DCF_Output`
- `Sensitivity`
- `Comps`
- `Story_Risk_Catalyst`
- `Assumption_Journal`
- `Action_Ledger`

---

## 6) Agent workflow (multi-turn)

### 6.1 Phase A: mandate + gaps
- Capture user objective and constraints.
- Detect missing high-impact inputs.
- Ask focused follow-up questions when needed.

### 6.2 Phase B: evidence collection
Gather and normalize:
- SEC filings (10-K/10-Q/8-K, XBRL facts)
- market/fundamental data
- estimates/guidance/transcripts (if available)
- macro/rates data
- industry/peer context and recent catalysts

### 6.3 Phase C: data quality checks
- Resolve unit mismatches (millions vs billions).
- Verify period consistency (FY/TTM/LTM).
- Flag stale or conflicting data.
- Write source-attributed raw facts to sheet.

### 6.4 Phase D: scenario design + assumption reasoning
For each scenario (pessimistic/base/optimistic), decide and log:
- revenue growth path
- margin trajectory
- reinvestment/capital intensity
- WACC components and capital structure assumptions
- terminal growth constraints

### 6.5 Phase E: valuation execution in Sheets
- Populate scenario inputs.
- Trigger formula recalculation.
- Read DCF outputs for each scenario.
- Compute weighted valuation through sheet formulas (`Scenario_Weights` + `DCF_Output`).

### 6.6 Phase F: sensitivity + competitive analysis
- Sensitivity grids (for example WACC x terminal growth, margin x growth).
- Peer set construction and sanity checks.
- Relative valuation context (multiples and narrative consistency).

### 6.7 Phase G: story synthesis + memo
- Build thesis linked to operating drivers.
- Tie scenario assumptions to qualitative narrative.
- Summarize upside/downside conditions and catalysts.
- Produce memo with citation mapping to evidence and sheet outputs.

### 6.8 Phase H: final validation
- hard checks pass
- citation coverage threshold met
- output completeness verified
- publish sheet + memo links

---

## 7) Tooling stack

### 7.1 Mandatory tools
- Google Sheets API tool:
  - copy template
  - write ranges/formulas
  - read outputs
  - append logs
- SEC EDGAR tool:
  - filings metadata
  - submissions/companyfacts
  - filing text/sections
- Market/fundamentals provider (Finnhub or equivalent):
  - price, market cap, shares, statements, estimates
- Web/news search tool:
  - catalysts
  - controversies
  - competitive developments

### 7.2 Recommended additional tools
- FRED/Treasury rates tool (risk-free, macro context).
- Earnings call transcripts tool.
- Corporate actions tool (splits/buybacks/dividends history).
- Sector/industry classification tool (GICS/NAICS mapping).
- Source reliability scorer / contradiction checker.
- Document extraction tool (tables from filings/pdfs).

### 7.3 Tool interface requirements
- Strict JSON schemas for all function calls.
- Minimal and explicit parameter sets.
- `tool_choice` controls for critical steps.
- Tool output must include provenance metadata:
  - source
  - timestamp
  - endpoint/document id

---

## 8) Guardrails and policy controls

### 8.1 Safety guardrails
- Prompt-injection mitigation:
  - untrusted text is treated as data, not instructions
- PII/privacy redaction in logs and prompts.
- Approval gate for high-impact writes/exports where needed.

### 8.2 Financial-quality guardrails
- `WACC > g` hard fail.
- Scenario weights sum to 100% hard fail.
- Weighted valuation must be formula-linked to scenario outputs hard fail.
- Diluted share sanity checks and bridge consistency.
- Memo numeric claims must map to sheet output range and source.

### 8.3 Citation requirements
- Every non-trivial numeric claim requires citation.
- Every major qualitative claim (thesis/risk/catalyst) requires source or explicit labeled judgment.

---

## 9) Logging and traceability

### 9.1 In-sheet logs
- `Action_Ledger` rows:
  - step
  - phase
  - tool
  - action
  - target range
  - short input/output summary
  - citation ids
- `Assumption_Journal` rows:
  - assumption key
  - scenario
  - value/unit
  - rationale
  - confidence
  - source links

### 9.2 System traces
Store run trace with:
- prompts/instructions version ids
- tool call payloads and responses
- sheet mutations
- validation results
- token/cost/time stats

---

## 10) Evaluation strategy

### 10.1 Automated checks
- contract tests for named ranges and required tabs
- no-offsheet-math check for final outputs
- scenario completeness and weights check
- citation coverage check

### 10.2 Quality evals
- rubric scoring for assumption quality and narrative coherence
- regression set across sectors/market regimes
- trace graders for tool-use correctness and policy compliance

### 10.3 Release gates
- fail if any hard financial invariant fails
- fail if missing citations above threshold
- fail if template contract drifts

---

## 11) Implementation roadmap

### Phase 1: foundation
- lock template contract and named ranges
- implement sheets engine operations + run copy lifecycle
- implement SEC + market + rates adapters

### Phase 2: reasoning loop
- multi-turn orchestrator
- scenario assumption generator with strict schemas
- in-sheet logging wiring

### Phase 3: valuation and narrative
- 3-scenario DCF execution + weighted output tab
- sensitivity and comps modules
- memo generation with citation mapping

### Phase 4: hardening
- trace storage + eval pipeline
- guardrails + approvals + retry policies
- benchmark suite and CI gates

---

## 12) Alignment notes for this repository
This PRD supersedes earlier single-pass DCF framing by making these mandatory:
- multi-turn clarification and assumption iteration
- scenario weighting as first-class output
- story-to-valuation coherence checks
- no model-side math transformations
- richer tooling for competitive and catalyst research

---

## 13) Reference docs (latest reviewed)

### OpenAI
- Agents guide: https://platform.openai.com/docs/guides/agents
- Safety in building agents: https://platform.openai.com/docs/guides/agent-builder-safety
- Function calling: https://platform.openai.com/docs/guides/function-calling
- Structured outputs: https://platform.openai.com/docs/guides/structured-outputs
- Using tools: https://platform.openai.com/docs/guides/tools
- Agents SDK: https://platform.openai.com/docs/guides/agents-sdk
- Agent evals: https://platform.openai.com/docs/guides/agent-evals
- Trace grading: https://platform.openai.com/docs/guides/trace-grading

### Anthropic
- Building effective agents: https://www.anthropic.com/engineering/building-effective-agents
- Tool use overview: https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview
- Claude Code SDK agent permissions: https://docs.claude.com/en/docs/claude-code/sdk/sdk-permissions
