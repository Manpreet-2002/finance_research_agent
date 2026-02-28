# Multi-Turn Finance Research Agent: Complete System Design (HLD + LLD)

Last updated: 2026-02-26

## 1. Scope
This document captures the complete system design of the US stocks finance research agent across:
1. deterministic valuation orchestration,
2. workbook and formula boundary enforcement,
3. tool/provider integration and source grounding,
4. memo generation with infographic contract checks,
5. API and frontend delivery for queued executions and artifacts,
6. persistence, failure semantics, and observability.

This is the authoritative architecture reference for implementation and operations.

## 2. Design Invariants
1. Final valuation math is formula-owned in Google Sheets and never computed off-sheet for terminal outputs.
2. Phase order is deterministic (`intake -> data_collection -> data_quality_checks -> assumptions -> model_run -> validation -> memo -> publish`).
3. All external interactions are via typed tool calls and validated payload schemas.
4. Citations are mandatory for non-trivial factual/numeric claims.
5. A run is operationally complete only when sheet and memo deliverables are both available.

## 3. Diagram Catalog
Mermaid sources and rendered assets are cataloged in:
- `docs/system_design/diagram_manifest.json`

Markdown intentionally contains no inline Mermaid blocks. All Mermaid definitions live in external `.mmd` files referenced by the manifest.

## 4. High-Level Architecture
### 4.1 System Context (`m01`)
![System Context](assets/diagram_m01_system_context.png)

References:
1. Manifest id: `m01`
2. Source: `docs/system_design/mermaid/diagram_m01_system_context.mmd`
3. Rendered: `docs/system_design/assets/diagram_m01_system_context.png`

### 4.2 Runtime Sequence (`m02`)
![Execution Sequence](assets/diagram_m02_phase_execution_sequence.png)

References:
1. Manifest id: `m02`
2. Source: `docs/system_design/mermaid/diagram_m02_phase_execution_sequence.mmd`
3. Rendered: `docs/system_design/assets/diagram_m02_phase_execution_sequence.png`

### 4.3 Guardrail Stack (`m03`)
![Guardrails](assets/diagram_m03_guardrails_and_contracts.png)

References:
1. Manifest id: `m03`
2. Source: `docs/system_design/mermaid/diagram_m03_guardrails_and_contracts.mmd`
3. Rendered: `docs/system_design/assets/diagram_m03_guardrails_and_contracts.png`

### 4.4 Memo Lineage (`m04`)
![Memo Artifact Lineage](assets/diagram_m04_memo_artifact_lineage.png)

References:
1. Manifest id: `m04`
2. Source: `docs/system_design/mermaid/diagram_m04_memo_artifact_lineage.mmd`
3. Rendered: `docs/system_design/assets/diagram_m04_memo_artifact_lineage.png`

## 5. Low-Level Design: Orchestration Core
### 5.1 Orchestrator LLD flow (`m05`)
![Orchestrator LLD](assets/diagram_m05_orchestrator_ll_d_flow.png)

References:
1. Manifest id: `m05`
2. Source: `docs/system_design/mermaid/diagram_m05_orchestrator_ll_d_flow.mmd`
3. Rendered: `docs/system_design/assets/diagram_m05_orchestrator_ll_d_flow.png`

### 5.2 Control-plane modules
| Module | Low-level responsibility |
|---|---|
| `ValuationRunner` | Creates `llm_client`, `sheets_engine`, `data_service`, `research_service`; invokes orchestrator and captures final `ValuationRunResult`. |
| `LangGraphFinanceAgent` | Owns state graph, prompt assembly, tool invocation loop, phase gating, finalize path. |
| `V1WorkflowStateMachine` | Canonical phase order and next-phase resolution. |
| `SkillRouter` + `SkillLoader` | Deterministic phase/global skill set + prompt context materialization. |

### 5.3 Core phase algorithm
Per phase, the agent executes:
1. load phase skills and global skills,
2. construct constrained prompt with phase contracts,
3. invoke LLM with explicit tool schema set,
4. validate/sanitize tool calls and dispatch through registry,
5. run phase exit checks,
6. attempt bounded repair loops when contracts fail,
7. move to next phase only on contract-complete state.

Finalize stage executes:
1. output readback and integrity checks,
2. citation and story writeback normalization,
3. sheet formatting and sharing hooks,
4. logbook append and final status write.

### 5.4 Key phase gates
1. `validation` gate: sensitivity + comps + checks contracts must pass.
2. `memo` gate: story contract fields (including `story_memo_hooks`) must satisfy schema and quality thresholds.
3. bounded repair loops use configured maximum passes (`max_validation_repair_passes`).

## 6. Low-Level Design: Tooling and Data Plane
### 6.1 Tool firewall
`LlmToolRegistry` provides:
1. strict input payload validation,
2. known-tool dispatch only,
3. sheet tool aliasing/normalization,
4. structured error signaling for rejected/invalid calls,
5. degradable behavior for selected non-critical upstream tools.

### 6.2 Tool groups
1. fundamentals/market/rates/news ingestion,
2. transcript/corporate actions/peer universe tools,
3. contradiction and consistency tools,
4. deterministic math helper,
5. sheets read/write tools (`sheets_write_named_ranges`, `sheets_read_named_ranges`, `sheets_read_outputs`, named table writes).

### 6.3 Provider integration pattern
Provider factory resolves runtime adapters so orchestration depends on normalized contracts:
1. SEC EDGAR/XBRL for filing-grounded metrics,
2. Finnhub and other market/fundamentals endpoints,
3. FRED/Treasury for rates/macro context,
4. Tavily/web/news for external context,
5. transcript/actions/peers providers for narrative and comp context.

### 6.4 Canonical + research packet construction
1. `DataService` builds canonical_dataset for core valuation inputs and citations.
2. `ResearchService` augments with news, transcript signals, corporate actions, peers, and contradiction rows.
3. Canonical artifact and tool call traces are persisted in `artifacts/canonical_datasets`.

## 7. Low-Level Design: Workbook and Sheet Compute Plane
### 7.1 Workbook contract
Authoritative template:
- `Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx`

Required tabs:
1. Inputs,
2. Dilution (TSM),
3. R&D Capitalization,
4. Lease Capitalization,
5. DCF,
6. Sensitivity,
7. Comps,
8. Checks,
9. Sources,
10. Story,
11. Output,
12. Agent Log.

### 7.2 Named-range ownership
1. Writable: assumptions (`inp_*`), story/source/log regions, comps table inputs.
2. Formula-owned: valuation engine outputs and calculation surfaces (`calc_*`, `out_*`).
3. Reads use explicit output contract (`read_outputs` and named-range reads).

### 7.3 Sheet write validation pipeline
On every write:
1. resolve named range/table target against workbook schema,
2. reject unknown or disallowed phase targets,
3. reject formula-owned overlaps,
4. coerce/validate payload shape and scalar/matrix semantics,
5. persist write and emit structured telemetry.

### 7.4 High-signal data contracts
1. `sources_table`: fixed 11-column schema with absolute URL and ISO date constraints.
2. `comps_table_full`: header + data rows, first data row ticker must equal target ticker, `Notes` quality constraints.
3. `story_memo_hooks`: strict 5-column schema with linkage/citation/confidence validation and no unresolved range tokens in prose.

## 8. Low-Level Design: Memo Generation Pipeline
### 8.1 Pipeline internals
`PostRunMemoService.generate(...)` executes:
1. precondition checks (`with_memo`, valuation status, spreadsheet id),
2. bundle build (`memo_bundle.json`) from sheet + canonical + research + citations,
3. chart planning (availability + planner + fallback),
4. render + validate infographics (count, coverage buckets, quality score),
5. bounded repair loop for failed chart contracts,
6. narrative composition with structured JSON response contract,
7. markdown/html rendering,
8. PDF rendering,
9. manifest write (`memo_manifest.json`) with artifacts, attempts, notes, errors.

### 8.2 Status model
Wrapper statuses:
1. `SKIPPED`
2. `COMPLETED`
3. `COMPLETED_WITH_MEMO_FAILURE`

Execution row status mapping:
1. execution `COMPLETED` only when valuation and memo both complete and PDF exists,
2. execution `FAILED` otherwise, with merged error details.

### 8.3 Serialization hardening
Memo bundle and manifest serialization uses custom JSON default (`_json_default`) plus `_json_dumps` to safely encode date/datetime-like values and prevent runtime failures on non-JSON-native types.

## 9. API + Queue + Worker LLD
### 9.1 Execution state machine (`m06`)
![Execution State Machine](assets/diagram_m06_execution_state_machine.png)

References:
1. Manifest id: `m06`
2. Source: `docs/system_design/mermaid/diagram_m06_execution_state_machine.mmd`
3. Rendered: `docs/system_design/assets/diagram_m06_execution_state_machine.png`

### 9.2 API endpoints
| Method | Route | Behavior |
|---|---|---|
| `POST` | `/api/v1/executions` | Validate ticker, create queued row, return `202`. |
| `GET` | `/api/v1/executions` | Paginated/filterable history (`ticker`, `status`, `from_utc`, `to_utc`). |
| `GET` | `/api/v1/executions/{id}` | Return execution record with computed artifact URLs. |
| `GET` | `/api/v1/executions/{id}/memo.pdf` | Serve memo artifact if execution row/path checks pass. |

### 9.3 Execution persistence model (SQLite)
Table: `executions`
1. identity: `id`, `run_id`, `ticker`, `company_name`,
2. lifecycle: `status`, `submitted_at_utc`, `started_at_utc`, `finished_at_utc`,
3. artifact links: `spreadsheet_id`, `spreadsheet_url`, `memo_pdf_path`,
4. diagnostics: `error_message`,
5. audit: `created_at_utc`, `updated_at_utc`.

Indexes:
1. status/submission index for queue/list operations,
2. ticker/submission index for ticker-specific history lookup.

### 9.4 Worker loop semantics
1. API startup initializes store and worker thread.
2. Worker repeatedly claims oldest queued row (`BEGIN IMMEDIATE` claim semantics).
3. Worker executes valuation then memo.
4. Worker marks terminal status atomically with status-specific fields.
5. Shutdown signals worker stop and joins thread.

## 10. Frontend LLD
### 10.1 UI module structure
1. `frontend/lib/api.ts`: typed fetch functions and error normalization.
2. `frontend/components/execution-dashboard.tsx`: submit form, polling loop, metrics, result table.
3. `frontend/app/page.tsx`: dashboard entry page.

### 10.2 UI behavior details
1. submission normalizes ticker to uppercase client-side,
2. polling interval: 10 seconds,
3. table fields: ticker, name, analyzed time (UTC), sheet link, memo link, status,
4. failed rows expose backend `error_message`,
5. API base URL configurable via `NEXT_PUBLIC_API_BASE_URL`.

## 11. Guardrails and Failure Semantics
### 11.1 Guardrail layers
1. run/phase budgets,
2. tool scope enforcement,
3. phase allowlists for sheet writes,
4. workbook schema and formula ownership protections,
5. phase exit contracts,
6. finalize auto-repair pass.

### 11.2 Failure classes
1. provider/network unavailability,
2. schema/shape violations,
3. citation/story/comps/sensitivity contract failures,
4. memo chart contract convergence failures,
5. PDF render failures,
6. terminal timeout/budget exhaustion.

### 11.3 Failure observability
1. execution row `error_message`,
2. run logs (`artifacts/run_logs/<run_id>.log`),
3. canonical tool call traces (`*_tool_calls.jsonl`),
4. memo manifest errors/attempt logs.

## 12. Operational Runbook
Backend API:
```bash
PYTHONPATH=. uv run uvicorn backend.app.api.main:app --host 127.0.0.1 --port 8000
```

Frontend:
```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Smoke test:
```bash
PYTHONPATH=. uv run scripts/smoke_test_langgraph_runner.py --ticker ORCL --env-file .env
```

## 13. Legacy Diagram Retention
No existing assets were deleted from `docs/system_design/assets` or `docs/system_design/excalidraw`.
Retained legacy diagram inventory is tracked in:
- `docs/system_design/diagram_manifest.json` under `retained_legacy_assets`.

## 14. Engineering Roadmap (Design-Driven)
1. Promote end-to-end API + memo artifact assertions to CI as required release gates.
2. Add authenticated API access and artifact authorization policy.
3. Introduce queue recovery tooling and operational replay CLI for failed runs.
4. Add deterministic dataset caching by `(ticker, provider, endpoint, as_of)` to improve reproducibility and cost control.
5. Add explicit memo quality rubric scoring and threshold-based fail-fast enforcement.
