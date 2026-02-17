# V1 Tool Stack Implementation (February 15, 2026)

This document records what was implemented for the Phase V1 mandatory tool stack and how it is wired in the backend.

Companion skill-pack document:
- `docs/architecture/v1-skill-pack-implementation-2026-02-15.md`
Companion orchestration document:
- `docs/architecture/v1-langgraph-orchestration-2026-02-15.md`

## Scope completed

Implemented and wired the following mandatory integrations:

1. Google Sheets API (OAuth mode, template copy/write/read/log append)
2. SEC EDGAR/XBRL fundamentals adapter
3. Finnhub market/fundamentals adapter (refined provenance notes)
4. Tavily web/news adapter (primary open-web search path)
5. FRED rates adapter (refined unit provenance)
6. Alpha Vantage transcript adapter
7. Alpha Vantage corporate actions adapter
8. Finnhub peer/sector discovery adapter
9. Rule-based source contradiction checker
10. Python LLM tool-call registry with strict input schemas

## Key backend modules added or updated

Core provider and infra changes:

- `backend/app/tools/http_client.py`
  - Added retry/backoff and standardized HTTP error handling (`ToolHttpError`).
  - Added `post_json` for providers requiring POST payloads (Tavily).

- `backend/app/core/settings.py`
  - Added/standardized env-driven settings for:
    - Google OAuth mode/paths
    - SEC user-agent/contact
    - Tavily and Alpha Vantage API keys
    - provider defaults aligned to V1 mixed strategy

- `backend/app/tools/provider_factory.py`
  - Added builder wiring for:
    - `TavilyNewsClient`
    - `AlphaVantageTranscriptClient`
    - `AlphaVantageCorporateActionsClient`
    - `FinnhubPeerUniverseClient`
    - SEC fundamentals with explicit user-agent
  - Research flow now prefers `WEB_SEARCH_PROVIDER` for story/evidence retrieval.

Provider adapters:

- `backend/app/tools/sec/client.py`
  - Implemented ticker -> CIK resolution and `companyfacts` parsing.
  - Extracts core fundamentals used by DCF inputs.

- `backend/app/tools/news/tavily.py`
  - Added Tavily search client mapping results into canonical `NewsItem`.

- `backend/app/tools/transcripts/alpha_vantage.py`
  - Added transcript retrieval and lightweight rule-based signal extraction.

- `backend/app/tools/corporate_actions/alpha_vantage.py`
  - Added split/dividend retrieval mapped to `CorporateAction`.

- `backend/app/tools/peer/finnhub.py`
  - Added peer-universe discovery and profile enrichment.

- `backend/app/tools/contradiction_checker/client.py`
  - Added numeric/text mismatch checks using source-priority ordering.

Sheets implementation:

- `backend/app/sheets/google_engine.py`
  - Concrete OAuth-backed Sheets/Drive engine for:
    - template copy
    - named range writes
    - output reads
    - logbook appends

LLM tool-call surface:

- `backend/app/tools/llm_tools.py`
  - Strict, schema-validated Python tool registry for orchestrator use.
  - Includes granular tool calls and aggregate fetch paths:
    - `fetch_fundamentals`
    - `fetch_market_snapshot`
    - `fetch_rates_snapshot`
    - `fetch_news_evidence`
    - `fetch_transcript_signals`
    - `fetch_corporate_actions`
    - `discover_peer_universe`
    - `check_source_contradictions`
    - `fetch_canonical_dataset`
    - `fetch_research_packet`

## Smoke tests added (separate scripts)

Added separate smoke tests under `scripts/`:

- `scripts/smoke_test_finnhub.py` (default ticker: `AAPL`)
- `scripts/smoke_test_fred.py` (default series: `DGS10`)
- `scripts/smoke_test_tavily.py` (default ticker: `AAPL`)
- `scripts/smoke_test_alpha_vantage_transcripts.py` (default ticker: `AAPL`)
- `scripts/smoke_test_alpha_vantage_corporate_actions.py` (default ticker: `AAPL`)
- `scripts/smoke_test_sec_edgar.py` (default ticker: `AAPL`)
- Existing Google Sheets smoke test retained:
  - `scripts/google_sheets_smoke_test.py`

Shared loader:

- `scripts/smoke_test_common.py`

## Architecture diagram (Excalidraw only)

Authoritative shareable diagram:

- https://excalidraw.com/#json=WAIZC38Cvi9so_RQ1GAg6,bIAI3iWtgKKj9m56aj1-Gw

![V1 Tool Architecture](../v1_tool_architecture.png)

## Verification status

Smoke checks run and passing on February 15, 2026:

1. Google Sheets smoke (`A11: 55`) passed
2. Finnhub smoke passed
3. FRED smoke passed
4. Tavily smoke passed
5. Alpha Vantage transcript smoke passed
6. Alpha Vantage corporate actions smoke passed
7. SEC EDGAR smoke passed

## Known limitations

1. Transcript signal extraction is intentionally lightweight and deterministic for V1 scaffolding quality.
2. Caching policy (`ticker + endpoint + period`) is deferred by decision.
3. Full orchestration usage in `ValuationRunner` is still pending wiring to these tools.
4. `pytest` execution in this environment requires `pytest` dependency installation before local test runs.
