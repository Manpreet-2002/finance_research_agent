# Repository Guidelines

## Mission
Codex's primary goal in this repository is to help build a high-quality, investment-banking-style, multi-turn US stocks finance research agent that, for a given ticker, produces:
- a high-quality Google Sheets valuation workbook
- a high-quality investment memo

This mission is authoritative for implementation decisions, prioritization, and quality bars.

## V2 goal (authoritative)
For V2, after the agent completes the spreadsheet workflow for a ticker, it must generate a local 3-5 page investment memo document that includes:
- revenue mix
- product mix
- company divisions and business segments
- management quality
- sectoral analysis
- detailed comps and peer analysis
- opportunities and risks
- descriptive company story
- explicit mapping from story to DCF and sensitivity outputs
- informative, high-quality infographics
- high-quality investment-banking-style writing

First order of business for V2:
- evaluate infographic creation tools and identify the stack that best fits this use case.

## Project Structure & Module Organization
This repository follows the V1 valuation-agent layout:
- `frontend/`: Next.js UI scaffold.
- `backend/`: FastAPI orchestration + tool adapters (package under `backend/app/`).
- `tests/`: unit/integration/eval structure.
- `docs/`: architecture notes, runbooks, and ADRs.
- `scripts/google_sheets_smoke_test.py`: V1 connectivity smoke test.
- `scripts/GOOGLE_SHEETS_SMOKE_TEST_SETUP.md`: OAuth setup/run steps.
- `us_stocks_valuation_agent_excelgraph_prd_system_design.md`: primary PRD/system design.
- `DCF_Skill_ExcelGraph_Logbook.md`: operational DCF + logbook contract.
- `phase_v1.md`: V1 implementation plan and mandatory scope.
- `pyproject.toml` and `uv.lock`: Python dependencies via `uv`.

## Build, Test, and Development Commands
Use `uv` for Python workflows:
- `uv sync`
- `uv run scripts/google_sheets_smoke_test.py --title test_graph_1`
- `uv run python -m py_compile scripts/google_sheets_smoke_test.py`

General repo commands:
- `git status`
- `rg --files`
- `rg -n "pattern" us_stocks_valuation_agent_excelgraph_prd_system_design.md`
- `rg -n "pattern" DCF_Skill_ExcelGraph_Logbook.md`
- `rg -n "pattern" phase_v1.md`
- `rg -n "pattern" docs/`
- `git log --oneline -n 10`

## Smoke test for multi turn agent command
- The ORCL (ticker name) smoke test command is:
  `PYTHONPATH=. uv run scripts/smoke_test_langgraph_runner.py --ticker ORCL --env-file .env`
- When asked to run a smoke test, monitor the active run to completion and do not restart it as "stalled" unless the configured LLM timeout has actually been hit.

## Coding Style & Naming Conventions
- Prefer descriptive domain names (`sheets_engine`, `valuation_run`, `logbook_entry`).
- Keep modules focused; separate data collection, modeling, and reporting.
- Keep Markdown concise with consistent heading depth.
- Use snake_case for Python files/functions and kebab-case for markdown filenames.

## Testing Guidelines
Automated tests are scaffolded but minimal.
- For docs changes, validate terminology and cross-reference consistency.
- For Sheets checks, run smoke test and verify output includes `A11: 55`.
- Add tests under `tests/` mirroring source paths.
- Prioritize tests for valuation invariants, sheet-contract compliance, and citation grounding.

## Finance agent operating contract (must follow)
- Start every run from a copied semi pre-populated Google Sheets template.
- Run a multi-turn workflow and ask for missing high-impact inputs when needed.
- Build a 3-scenario DCF (`pessimistic`, `neutral/base`, `optimistic`) and set scenario weights.
- Keep all valuation math in Google Sheets formulas; never do final model math off-sheet.
- Log assumption rationale, story rationale, and valuation rationale directly in-sheet.
- Perform sensitivity analysis and competitive analysis tied to company, industry, and market context.
- Tie valuation outputs to a coherent narrative in an Aswath-Damodaran-style story-to-numbers framework.
- Produce both deliverables for each run: high-quality sheet + high-quality memo.
- Use citations for non-trivial numeric and factual claims.

## Workbook alignment contract (must follow)
Authoritative template/artifact basis:
- `Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx`

The agent must align skills and tool writes to this template structure:
- Tabs: `Inputs`, `Dilution (TSM)`, `R&D Capitalization`, `Lease Capitalization`, `DCF`, `Sensitivity`, `Comps`, `Checks`, `Sources`, `Story`, `Output`, `Agent Log`.
- Scenario inputs and weights: `inp_pess_*`, `inp_base_*`, `inp_opt_*`, `inp_w_pess`, `inp_w_base`, `inp_w_opt`.
- Core outputs: `out_value_ps_pess`, `out_value_ps_base`, `out_value_ps_opt`, `out_value_ps_weighted`, `out_equity_value_weighted`, `out_enterprise_value_weighted`.
- Run/log anchors: `log_run_id`, `log_status`, `log_actions_firstrow`, `log_assumptions_firstrow`, `log_story_firstrow`.

Execution rule:
- All valuation math must remain formula-driven inside the workbook/sheet model; agent code only writes inputs, reads outputs, and logs rationale/provenance.

## Mandatory V1 tool stack (implementation scope)
All tools below are in-scope mandatory integrations for V1:
- Google Sheets API
- SEC EDGAR/XBRL
- fundamentals/market data provider (Finnhub primary)
- web/news search (Tavily primary)
- rates/macro provider (FRED/Treasury)
- earnings transcript provider
- corporate actions provider
- sector/peer classification provider
- source contradiction checker

## Security & Credentials
- Never commit OAuth secrets or tokens.
- Keep `credentials.json`, `token.json`, and service account keys out of Git.
- Use environment variables or ignored local files for credentials.

## Diagram instruction
- If asked to generate diagrams, use Excalidraw MCP when available.
- When generating Excalidraw JSON, do not output skeleton elements. For every text element include width, height, baseline, opacity=100, fontFamily=1, textAlign='center', verticalAlign='middle', lineHeight=1.25, and escape all newlines as \n. Bind text to its container using containerId + boundElements.
- Do not use label fields. Every label must be a separate type:'text' element. If text is inside a shape, bind it via containerId and boundElements. Output fully-qualified elements (run convertToExcalidrawElements)
- Provide a shareable Excalidraw link.
