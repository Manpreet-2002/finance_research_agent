# Finance Research Agent

V1 scaffolding for a US stocks valuation agent with Google Sheets as the deterministic modeling engine.

## Current focus
- Google Sheets API smoke test: `scripts/google_sheets_smoke_test.py`
- Provider smoke tests:
  - `scripts/smoke_test_finnhub.py`
  - `scripts/smoke_test_fred.py`
  - `scripts/smoke_test_tavily.py`
  - `scripts/smoke_test_alpha_vantage_transcripts.py`
  - `scripts/smoke_test_alpha_vantage_corporate_actions.py`
  - `scripts/smoke_test_sec_edgar.py`
- V1 architecture and product plan: `us_stocks_valuation_agent_excelgraph_prd_system_design.md`
- DCF skill contract and logbook behavior: `DCF_Skill_ExcelGraph_Logbook.md`

## Repository layout (V1)
- `frontend/`: Next.js UI scaffold location
- `backend/`: FastAPI orchestration and tool adapters scaffold
- `tests/`: unit, integration, and eval suites
- `docs/`: architecture notes, runbooks, and ADRs
- `scripts/`: operational scripts (Google Sheets smoke test)

## Quick start
```bash
uv sync
uv run scripts/google_sheets_smoke_test.py --title test_graph_1
uv run scripts/smoke_test_finnhub.py --ticker AAPL
uv run scripts/smoke_test_fred.py --series-id DGS10
```
