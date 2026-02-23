# Multi-Turn Finance Research Agent: Architecture Design
**As-Built System + Target-State Architecture**

Last updated: 2026-02-22

## 1. Architecture First: System at a Glance
This system is a deterministic, multi-phase valuation-and-memo pipeline with a strict sheet-math boundary. The architecture is designed so that:
1. Orchestration controls phase order and policy.
2. Tools provide all external and sheet IO through typed contracts.
3. Spreadsheet formulas remain the single source of valuation truth.
4. Story and memo generation are constrained by citation and schema guardrails.

### 1.1 System context
![As-built system context](assets/diagram_01_as_built_architecture.png)

Excalidraw link: [diagram_01_as_built_architecture](https://excalidraw.com/#json=GRT9XBTL5-t8ICChKKaSJ,VJm-TAdpbmym5K6Blsi7Ww)  
Excalidraw JSON: `docs/system_design/excalidraw/diagram_01_as_built_architecture.excalidraw.json`

### 1.2 Deterministic execution topology
![Deterministic phase execution](assets/diagram_02_phase_sequence.png)

Excalidraw link: [diagram_02_phase_sequence](https://excalidraw.com/#json=Kf7zFFF5LHM7xpQyFXssy,kJyTCSSFu5FZW66_higlDw
)  
Excalidraw JSON: `docs/system_design/excalidraw/diagram_02_phase_sequence.excalidraw.json`

## 2. Core Components and Responsibilities
| Layer | Component | Responsibility | Primary code |
|---|---|---|---|
| Entry | `ValuationRunner` | Runtime wiring, dependency assembly, run lifecycle logging | `backend/app/orchestrator/valuation_runner.py:26` |
| Orchestration | `LangGraphFinanceAgent` | Build/execute deterministic graph, phase prompts, tool loops, contract exits | `backend/app/orchestrator/langgraph_finance_agent.py:230` |
| State machine | `V1WorkflowStateMachine` | Canonical phase order and transitions | `backend/app/orchestrator/state_machine.py:21` |
| Skills | `SkillSpec` catalog + router + loader | Phase-aware prompt composition and tool/range scoping intent | `backend/app/skills/catalog.py:21`, `backend/app/skills/router.py:12`, `backend/app/skills/loader.py:10` |
| Tooling | `LlmToolRegistry` | Tool schema validation, typed tool dispatch, degradable tool behavior | `backend/app/tools/llm_tools.py:205` |
| Data plane | `DataService` + `ResearchService` | Canonical dataset and extended research packet construction | `backend/app/tools/data_service.py:18`, `backend/app/tools/research_service.py:22` |
| Provider wiring | `provider_factory` | Runtime provider selection and adapter construction | `backend/app/tools/provider_factory.py:47` |
| Sheet compute | `GoogleSheetsEngine` | Template copy, named-range/table reads-writes, output extraction, schema inspection | `backend/app/sheets/google_engine.py:63` |
| Workbook contract | `WorkbookContract` | Required tabs and named-range pattern validation | `backend/app/workbook/contract.py:137` |

## 3. As-Built Architecture
### 3.1 Control plane
Control flow starts in `ValuationRunner`, which constructs all concrete services and then delegates to `LangGraphFinanceAgent`.

Control-plane invariants:
1. Orchestrator graph is fixed-order and deterministic by construction.
2. Each phase has explicit skill routing and tool allowlisting.
3. Finalization performs hard output/contract checks before run completion.

Key anchors:
1. Graph construction: `backend/app/orchestrator/langgraph_finance_agent.py:351`
2. Phase iteration constraints: `backend/app/orchestrator/langgraph_finance_agent.py:1320`
3. State translation to final result: `backend/app/orchestrator/langgraph_finance_agent.py:342`

### 3.2 Intelligence plane
The model does not operate with unconstrained free-form autonomy. It is guided by:
1. Phase-specific system prompts.
2. Skill markdown bundles.
3. Shared quality and reference bundles.
4. Tool schema and allowlist constraints.

Key anchors:
1. Prompt assembly with skill content: `backend/app/orchestrator/langgraph_finance_agent.py:1825`
2. Hard constraints in prompt: `backend/app/orchestrator/langgraph_finance_agent.py:1904`
3. Skill loading: `backend/app/skills/loader.py:16`

### 3.3 Data and provider plane
The architecture uses adapter-based provider composition so the orchestrator depends on normalized contracts, not provider-specific payloads.

Provider construction flow:
1. Resolve provider names from settings.
2. Build concrete clients per domain.
3. Inject into `DataService` and `ResearchService`.
4. Expose through tool handlers.

Key anchors:
1. Core provider resolution: `backend/app/tools/provider_factory.py:47`
2. Research provider resolution: `backend/app/tools/provider_factory.py:57`
3. Data aggregation: `backend/app/tools/data_service.py:32`
4. Research packet aggregation: `backend/app/tools/research_service.py:36`

### 3.4 Spreadsheet compute plane
This plane is intentionally strict. All workbook interactions must be via named ranges/named tables and sheet APIs.

Engine responsibilities:
1. Copy template into run-scoped spreadsheet.
2. Validate named range targets on writes.
3. Coerce/validate payload shapes against named-range bounds.
4. Read outputs from fixed output contract ranges.
5. Append run summary to logbook.

Key anchors:
1. Template copy: `backend/app/sheets/google_engine.py:82`
2. Named-range write path: `backend/app/sheets/google_engine.py:121`
3. Output read path: `backend/app/sheets/google_engine.py:153`
4. Named-range read path: `backend/app/sheets/google_engine.py:175`
5. Schema load and formula-owned detection: `backend/app/sheets/google_engine.py:711`

## 4. Phase-by-Phase Architecture
### 4.1 Phase catalog
| Phase | Primary objective | Typical tool domains |
|---|---|---|
| `intake` | Capture ticker/mandate and initialize run log context | Sheets |
| `data_collection` | Gather canonical and research evidence | SEC, fundamentals/market, rates, transcripts/actions/peers, sheets |
| `data_quality_checks` | Enforce source/schema quality before assumptions | Contradiction checker, sheets |
| `assumptions` | Set scenario assumptions and weights | Canonical/research refresh, contradiction checks, sheets |
| `model_run` | Trigger and read formula-driven outputs | Sheets outputs |
| `validation` | Validate sensitivity/comps/citation integrity | Sheets, market/fundamentals/news/peers/math, contradiction checker |
| `memo` | Build story-to-numbers linkage and memo hooks | Sheets + LLM guidance |
| `publish` | Final handoff and closure prep | Sheets outputs/reads |

### 4.2 Phase transition enforcement
Transition discipline is enforced by:
1. Fixed order from `WorkflowPhase` enum and `_ORDER` tuple.
2. Phase exit contract checks for `validation` and `memo`.
3. Guardrail continuation prompts when contracts are incomplete.

Key anchors:
1. State machine ordering: `backend/app/orchestrator/state_machine.py:24`
2. Exit contract gate: `backend/app/orchestrator/langgraph_finance_agent.py:1534`
3. Validation exit checks: `backend/app/orchestrator/langgraph_finance_agent.py:1547`
4. Memo exit checks: `backend/app/orchestrator/langgraph_finance_agent.py:1551`

## 5. Architecture Deep Dive
### 5.1 Skills
#### 5.1.1 Skill model
Each skill declares:
1. `skill_id`
2. `phase`
3. `required_tools`
4. `workbook_tabs`
5. `named_ranges`

Anchor: `backend/app/skills/catalog.py:8`

#### 5.1.2 Routing semantics
Routing is deterministic and additive:
1. Include all skills where `skill.phase == current_phase`.
2. Include all `global` skills every phase.

Anchor: `backend/app/skills/router.py:17`

#### 5.1.3 Loading semantics
Skill loader composes three prompt sources:
1. Skill-local `SKILL.md`.
2. Shared quality bundle references.
3. Phase reference bundle.

Anchor: `backend/app/skills/loader.py:20`

#### 5.1.4 Current catalog shape
Current as-built catalog has 16 skills spanning global + 8 phases.

| Phase bucket | Skill count |
|---|---:|
| global | 1 |
| intake | 1 |
| data_collection | 5 |
| data_quality_checks | 1 |
| assumptions | 1 |
| model_run | 1 |
| validation | 3 |
| memo | 2 |
| publish | 1 |

### 5.2 Tools
#### 5.2.1 Registry architecture
`LlmToolRegistry` acts as a typed execution firewall:
1. Validates required schema fields before call.
2. Dispatches only known tool names.
3. Captures tool timing and failures.
4. Applies degradable behavior for selected upstream tools.

Anchors:
1. Registry class: `backend/app/tools/llm_tools.py:205`
2. Validation path: `backend/app/tools/llm_tools.py:247`
3. Degradable set: `backend/app/tools/llm_tools.py:24`

#### 5.2.2 Tool groups
As-built registry exposes 18 tools across:
1. Source fetch tools (SEC/fundamentals/market/rates/news/transcripts/actions/peers).
2. Canonical artifact tools.
3. Deterministic math tool.
4. Sheets write/read tools.

Anchor: `backend/app/tools/llm_tools.py:261`

#### 5.2.3 Sheets tool contract discipline
Sheets tools enforce:
1. Read-only runtime range protection.
2. No mixed `story_*` and `comps_*` writes in one call.
3. Numeric normalization for rates and money scales.
4. Strict table schema validation (`sources`, logs, comps).

Anchors:
1. Read-only/mixed-write checks: `backend/app/tools/llm_tools.py:713`
2. Range normalization: `backend/app/tools/llm_tools.py:769`
3. Table validation dispatch: `backend/app/tools/llm_tools.py:884`

### 5.3 Guardrails
Guardrails exist at six layers.

Layer 1: Invocation budgets
1. Max turns per phase.
2. Max wall-clock per phase.
3. Max model invoke timeout.

Anchor: `backend/app/orchestrator/langgraph_finance_agent.py:240`

Layer 2: Tool scope safety
1. Sheets calls are forced to active run sheet.
2. Wrong/missing `spreadsheet_id` is overridden/injected.

Anchor: `backend/app/orchestrator/langgraph_finance_agent.py:3254`

Layer 3: Phase write allowlists
1. Named-range writes blocked if not in phase allowlist.
2. Named-table writes blocked if table not phase-approved.
3. Mixed story/comps write payload blocked.

Anchor: `backend/app/orchestrator/langgraph_finance_agent.py:3278`

Layer 4: Sheet model safety
1. Unknown named range writes blocked.
2. Formula-owned range writes blocked.
3. Shape mismatch writes blocked.

Anchors:
1. Unknown/blocked writes: `backend/app/sheets/google_engine.py:623`
2. Shape coercion/mismatch logic: `backend/app/sheets/google_engine.py:645`

Layer 5: Exit contracts
1. Validation cannot exit without sensitivity+comps contracts.
2. Memo cannot exit without story contract completion.

Anchors:
1. Exit gate: `backend/app/orchestrator/langgraph_finance_agent.py:1534`
2. Sensitivity validator: `backend/app/orchestrator/langgraph_finance_agent.py:2050`
3. Comps validator: `backend/app/orchestrator/langgraph_finance_agent.py:2563`
4. Story validator: `backend/app/orchestrator/langgraph_finance_agent.py:2767`

Layer 6: Finalize auto-repair
1. Citation/story writeback enforcement.
2. Story memo hook normalization.
3. Final output integrity checks and logbook append.

Anchors:
1. Sources/story citation writeback: `backend/app/orchestrator/langgraph_finance_agent.py:2942`
2. Story hook normalization: `backend/app/orchestrator/langgraph_finance_agent.py:3055`

### 5.4 Evals
#### 5.4.1 Current as-built eval posture
Current automated coverage is unit-heavy:
1. 92 unit tests across guardrails, tools, sheets range behavior, providers, and skill catalog.
2. `tests/integration` and `tests/evals` are scaffold-only.

High-signal existing suites:
1. `tests/unit/test_orchestrator_guardrails.py`
2. `tests/unit/test_llm_tools.py`
3. `tests/unit/test_google_sheets_engine_ranges.py`
4. `tests/unit/test_skill_catalog.py`
5. `tests/unit/test_workbook_contract.py`

#### 5.4.2 Target-state eval architecture
Recommended multi-tier eval stack:
1. Contract eval tier: workbook tab/range/schema conformance.
2. Tool-policy eval tier: allowlist and scope-injection adversarial tests.
3. Sheet-math eval tier: invariant checks (`WACC > g`, scenario weights sum, sensitivity grid shape).
4. Citation eval tier: coverage, diversity, contradiction resolution traceability.
5. Memo eval tier: story-to-numbers linkage rubric and citation-grounding score.
6. End-to-end regression tier: deterministic replay with artifact diffing.

### 5.5 Citations
#### 5.5.1 As-built citation architecture
Citation handling is first-class in model and sheet contracts:
1. Canonical and research tools return citations with source + endpoint + time.
2. `sources_table` requires strict schema and valid URL/date/citation identifiers.
3. Story citation cells must contain valid tokens.
4. Finalize can backfill source rows and story citation rows from tool-call artifacts.

Anchors:
1. Citation schema constants: `backend/app/tools/llm_tools.py:70`
2. Sources contract validator: `backend/app/orchestrator/langgraph_finance_agent.py:2698`
3. Story citation checks: `backend/app/orchestrator/langgraph_finance_agent.py:2928`
4. Tool-call artifact persistence: `backend/app/orchestrator/langgraph_finance_agent.py:1202`

#### 5.5.2 Source priority policy
Policy ordering is explicit:
1. `SEC/FRED/Treasury` > `Alpha Vantage` > `Finnhub` > `web/news`.

Anchor: `phase_v1.md:502`

### 5.6 Sheet Math Architecture
#### 5.6.1 Non-negotiable boundary
All final valuation math is formula-owned in the workbook. Agent runtime is limited to:
1. Writing assumptions/metadata/log/story/comps/source inputs.
2. Reading output contract ranges.
3. Running checks and validations.

Contract anchors:
1. Operating contract rule: `AGENTS.md:59`
2. Workbook execution rule: `AGENTS.md:77`

#### 5.6.2 Workbook interface contract
Required workbook shape is codified through:
1. Required tabs list.
2. Required named-range pattern set.
3. Contract validator at run-sheet initialization.

Anchors:
1. Required tabs: `backend/app/workbook/contract.py:13`
2. Required range patterns: `backend/app/workbook/contract.py:29`
3. Contract validation path: `backend/app/orchestrator/langgraph_finance_agent.py:1990`

#### 5.6.3 Formula protection path
Formula protection uses two mechanisms:
1. Name-based formula-owned range classification.
2. Bounds-level overlap checks to prevent accidental writes.

Anchors:
1. Formula-owned block in writes: `backend/app/sheets/google_engine.py:637`
2. Formula-owned bounds materialization: `backend/app/sheets/google_engine.py:742`

#### 5.6.4 Sheet-math ownership table
| Concern | Owned by agent | Owned by sheet formulas |
|---|---|---|
| Scenario assumptions (`inp_*`) | Yes | No |
| Scenario weights (`inp_w_*`) | Yes | No |
| DCF cash-flow mechanics | No | Yes |
| Terminal value and WACC propagation | No | Yes |
| Weighted valuation outputs (`out_*`) | No | Yes |
| Story/citation linkage text | Yes | No |
| Final output readout | Read only | Produced by formulas |

## 6. Workbook and Data Contracts
### 6.1 Workbook contract
Workbook contract includes:
1. Fixed tab taxonomy across Inputs/Model/Validation/Story/Output/Log planes.
2. Named-range pattern contract to guarantee tool compatibility.
3. Contract validation prior to phase execution.

Anchors:
1. Template filename: `backend/app/workbook/contract.py:9`
2. Tab contract: `backend/app/workbook/contract.py:13`
3. Range pattern contract: `backend/app/workbook/contract.py:29`

### 6.2 Canonical dataset contract
Canonical dataset prefill is designed to reduce early-phase ambiguity while keeping source provenance.

Key properties:
1. Consolidated fundamentals/market/rates/news into a normalized schema.
2. Carries citation metadata and quality report for required sheet inputs.
3. Feeds initialization writes before phase turns begin.

Anchors:
1. Dataset assembly: `backend/app/tools/data_service.py:32`
2. Canonical input tool: `backend/app/tools/llm_tools.py:465`
3. Init use in orchestrator: `backend/app/orchestrator/langgraph_finance_agent.py:383`

## 7. Failure Semantics and Reliability
### 7.1 Failure classes
Failure classes in as-built architecture:
1. Tool payload/schema failure.
2. Provider degradation.
3. Guardrail rejection.
4. Contract incompleteness.
5. Timeout-bound LLM invoke failure.

### 7.2 Reliability mechanisms
Reliability is delivered through:
1. Time-bounded execution and explicit hard-fail exceptions.
2. Degradable tool behavior for non-critical providers.
3. Guardrail-repair loops when phase contracts are incomplete.
4. Finalize-stage auto-repair for citations/story hooks.
5. Structured artifact trace (`tool_calls.jsonl`) for replay/debug.

## 8. Security and Operational Boundaries
Security and credential posture from repository policy:
1. OAuth secrets and tokens must never be committed.
2. Google credentials must remain in ignored local files or env vars.
3. Runtime should use configured auth modes and provider keys from settings.

Policy anchors:
1. `AGENTS.md:91`
2. `phase_v1.md:515`

## 9. Target-State Architecture Improvements
### 9.1 Control and policy
1. Extract guardrails into a versioned policy engine with rule IDs and machine-readable outcomes.
2. Add explicit phase-level SLOs and budget telemetry by rule class.

### 9.2 Tooling and data
1. Introduce cache orchestration by `ticker+endpoint+period+as_of` for deterministic replay and cost control.
2. Add provider confidence and freshness metadata to every normalized field, not just citation row text.

### 9.3 Sheet math and model quality
1. Add preflight static shape checks for all named-range writes before dispatch.
2. Add compile-time range ownership maps to separate formula-owned vs input-owned namespaces explicitly.
3. Add deterministic sensitivity/comps revalidation gate before publish.

### 9.4 Evals and release safety
1. Promote integration and eval tiers to first-class CI gates.
2. Add memo rubric scoring and citation-grounding regression thresholds.
3. Add run artifact diffing for deterministic release comparisons.

## 10. Additional Excalidraw Diagram
### 10.1 Sheet-math architecture boundary
![Sheet-math architecture boundary](assets/diagram_03_sheet_math_boundaries.png)

Excalidraw link: [diagram_03_sheet_math_boundaries](https://excalidraw.com/#json=2enOtJsb8TlKiOOZSIR4i,zthYqLd-9Jtl_49AWAmj0Q)  
Excalidraw JSON: `docs/system_design/excalidraw/diagram_03_sheet_math_boundaries.excalidraw.json`

## 11. External References
### 11.1 OpenAI
1. [Function calling | OpenAI API](https://developers.openai.com/api/docs/guides/function-calling/)
2. [Evaluation best practices | OpenAI API](https://developers.openai.com/api/docs/guides/evaluation-best-practices/)
3. [Production best practices | OpenAI API](https://developers.openai.com/api/docs/guides/production-best-practices/)

### 11.2 Anthropic
1. [Implement tool use (Anthropic Docs)](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implement-tool-use)
2. [System prompts (Anthropic Docs)](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/system-prompts)

### 11.3 Platform and data APIs
1. [Google Sheets API concepts](https://developers.google.com/workspace/sheets/api/guides/concepts)
2. [Google Sheets `values.batchUpdate`](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchUpdate)
3. [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
4. [FRED API docs](https://fred.stlouisfed.org/docs/api/fred/)
5. [Tavily Search API reference](https://docs.tavily.com/documentation/api-reference/endpoint/search)
6. [Alpha Vantage API docs](https://www.alphavantage.co/documentation/)
7. [Finnhub API docs](https://finnhub.io/docs/api)
8. [LangGraph docs](https://langchain-ai.github.io/langgraph/)
9. [Damodaran narrative-to-numbers context](https://aswathdamodaran.blogspot.com/2023/02/investing-in-end-times-narrative.html)
