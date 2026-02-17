# Backend (V1)

Scaffold for the FastAPI orchestration layer described in the PRD.

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

## Smoke test
- `uv run scripts/smoke_test_langgraph_runner.py --ticker AAPL`
