# Backend (V1)

FastAPI orchestration layer for valuation execution intake and history APIs.

## Responsibilities
- orchestrate valuation runs
- call data tools (SEC, market data, rates)
- write/read Google Sheets ranges
- append run/event logbook rows
- invoke LLM for memo generation (provider: Google, model family: Gemini 3)

## Runtime stack baseline
- `langchain-google-genai` `4.x`
- `langchain-core` `1.x` (transitive)
- `langgraph` `1.x`

This baseline is required for Gemini thought-signature-safe tool calling with `gemini-3-pro-preview`.

## Current scaffold
- `app/core/settings.py`: runtime config loader
- `app/schemas/valuation_run.py`: run payload types
- `app/sheets/engine.py`: Sheets engine interface
- `app/sheets/google_engine.py`: OAuth-backed Google Sheets/Drive implementation
- `app/orchestrator/valuation_runner.py`: run orchestration skeleton
- `app/orchestrator/langgraph_finance_agent.py`: deterministic phase graph orchestrator (LangGraph + LangChain)
- `app/llm/client.py`: LLM client interface
- `app/llm/langchain_gemini.py`: Gemini chat adapter for LangChain tool-calling
- `app/tools/contracts.py`: canonical data and citation contracts
- `app/tools/data_service.py`: unified tool-layer service facade
- `app/tools/provider_factory.py`: env-driven provider wiring
- `app/tools/fundamentals/client.py`: fundamentals interface + SEC adapter slot
- `app/tools/fundamentals/finnhub.py`: Finnhub fundamentals adapter
- `app/tools/market/client.py`: market interface
- `app/tools/market/finnhub.py`: Finnhub market adapter
- `app/tools/rates/client.py`: rates interface + static fallback adapter
- `app/tools/rates/fred.py`: FRED rates adapter
- `app/tools/news/client.py`: news interface
- `app/tools/news/finnhub.py`: Finnhub news adapter
- `app/tools/news/tavily.py`: Tavily web-search adapter
- `app/tools/sec/client.py`: SEC EDGAR/XBRL fundamentals adapter
- `app/tools/transcripts/alpha_vantage.py`: Alpha Vantage transcript adapter
- `app/tools/corporate_actions/alpha_vantage.py`: Alpha Vantage corporate actions adapter
- `app/tools/peer/finnhub.py`: Finnhub peer universe adapter
- `app/tools/llm_tools.py`: strict Python tool-call registry for orchestrator/LLM
- `app/api/main.py`: FastAPI app entrypoint
- `app/api/executions/router.py`: ticker submission/history endpoints
- `app/api/executions/store.py`: SQLite execution persistence
- `app/api/executions/service.py`: single-worker queue processor

## Smoke test
- `uv run scripts/smoke_test_langgraph_runner.py --ticker AAPL`

## API run
Start backend API locally:

```bash
PYTHONPATH=. uv run uvicorn backend.app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Endpoints
- `GET /healthz`
- `POST /api/v1/executions` with `{ "ticker": "AAPL" }`
- `GET /api/v1/executions`
- `GET /api/v1/executions/{execution_id}`
- `GET /api/v1/executions/{execution_id}/memo.pdf`

### Runtime notes
- Execution lifecycle statuses: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`
- Execution persistence defaults to `artifacts/api/executions.db`
- Timestamps are returned in UTC ISO 8601 format
