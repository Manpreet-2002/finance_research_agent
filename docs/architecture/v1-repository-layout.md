# V1 repository layout

This layout follows the PRD layering for implementation.

## Directory map
- `frontend/`: Next.js UI
- `backend/`: FastAPI orchestration, tools, Sheets adapter
- `tests/`: unit, integration, eval suites
- `docs/`: architecture/runbooks/ADRs
- `scripts/`: utility scripts (for example Google Sheets smoke tests)

## Backend package map
- `backend/app/core/`: runtime settings and shared internals
- `backend/app/schemas/`: request/response and domain contracts
- `backend/app/orchestrator/`: run orchestration logic
- `backend/app/sheets/`: Google Sheets compute adapter
- `backend/app/tools/`: external data source clients + provider factory
- `backend/app/llm/`: provider adapters (Gemini 3 in V1)
