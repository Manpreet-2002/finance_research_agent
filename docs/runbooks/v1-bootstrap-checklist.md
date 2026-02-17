# V1 bootstrap checklist

1. Sync Python dependencies: `uv sync`
2. Configure OAuth creds (`credentials.json`) and keep secrets out of Git.
3. Run Sheets smoke test:
   - `uv run scripts/google_sheets_smoke_test.py --title test_graph_1`
4. Set runtime env from `.env.example`:
   - `LLM_PROVIDER=google`
   - `LLM_MODEL=gemini-3`
5. Confirm template + logbook files exist in Drive before backend automation.
