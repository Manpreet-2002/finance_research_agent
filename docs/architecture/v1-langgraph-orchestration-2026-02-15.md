# V1 LangGraph Orchestration Implementation (February 15, 2026)

This document records the deterministic multi-turn orchestration layer implemented with LangGraph + LangChain and Gemini.

## Runtime dependency baseline (updated)

- `langchain-google-genai`: `4.x`
- `langchain-core`: `1.x`
- `langgraph`: `1.x`

Reason: Gemini tool-calling with thought signatures requires the newer integration line to avoid provider-side `thought_signature` failures in multi-turn tool loops.

## Scope implemented

1. Deterministic phase graph:
- `intake -> data_collection -> data_quality_checks -> assumptions -> model_run -> validation -> memo -> publish`

2. Skill wiring:
- For each phase, the orchestrator loads phase `SKILL.md` files from `skills/<skill-id>/SKILL.md`.
- Shared quality/evidence bundle is injected from:
  - `skills/finance-quality-bar-and-evidence/SKILL.md`
  - selected references under `skills/finance-quality-bar-and-evidence/references/`

3. Tool wiring to LLM:
- LangChain tool wrappers are generated from `backend/app/tools/llm_tools.py` JSON schemas.
- Tool availability is phase-scoped via `SkillSpec.required_tools` in catalog.

4. Google Sheets policy:
- Sheet operations are tool-based and API-driven.
- LLM runtime is named-range-only (`sheets_write_named_ranges`, `sheets_read_named_ranges`) with named-table writes/appends (`sheets_write_named_table`, `sheets_append_named_table_rows`).
- Final valuation outputs are read from `out_*` ranges.

5. No-HITL policy:
- No user interrupt/resume in V1 orchestration.
- Missing high-impact inputs are handled via conservative defaults and logged in phase summaries.

## Key modules

- `backend/app/orchestrator/langgraph_finance_agent.py`
  - deterministic graph construction
  - phase execution loop
  - LangChain tool-calling turns
  - final output validations and closeout

- `backend/app/orchestrator/valuation_runner.py`
  - dependency assembly
  - provider services + sheets engine + skill loader
  - sec client wiring for filing-grounded tool access

- `backend/app/llm/langchain_gemini.py`
  - Gemini model adapter (`LLM_PROVIDER=google`, `LLM_MODEL=gemini-3`)

- `backend/app/tools/llm_tools.py`
  - expanded tool surface:
    - `fetch_sec_filing_fundamentals`
    - `sheets_read_named_ranges`
    - `sheets_write_named_table`
    - `sheets_append_named_table_rows`

## Result contract

`ValuationRunResult` now includes:
- `spreadsheet_id`
- `memo_markdown`
- `citations_summary`
- `pending_questions` (empty tuple for no-HITL mode)

## Smoke test entrypoint

- `scripts/smoke_test_langgraph_runner.py`

Run:
- `uv run scripts/smoke_test_langgraph_runner.py --ticker AAPL`
