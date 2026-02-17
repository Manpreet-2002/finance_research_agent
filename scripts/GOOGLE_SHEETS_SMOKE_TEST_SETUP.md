# Google Sheets Smoke Test Setup

This setup enables `scripts/google_sheets_smoke_test.py` to create a sheet named `test_graph_1`, write `1..10` into `A1:A10`, set `A11` to `=SUM(A1:A10)`, and verify `A11 == 55`.

## 1) Enable API access
1. Create or choose a Google Cloud project.
2. Enable **Google Sheets API** in that project.
3. Create an **OAuth client** of type **Desktop app**.
4. Download the client JSON as `credentials.json` in the repository root.
5. Add your account as a **Test user** on the OAuth consent screen if required.

## 2) Install uv and sync dependencies
If `uv` is not installed:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Sync dependencies from `pyproject.toml`:
```bash
uv sync
```

## 3) Provide credentials
Default auth uses OAuth user credentials from `credentials.json`.

Optional overrides:
- `GOOGLE_OAUTH_CLIENT_SECRET_FILE` (default: `credentials.json`)
- `GOOGLE_OAUTH_TOKEN_FILE` (default: `token.json`)

Service-account auth is still supported only if explicitly configured:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/absolute/path/to/service-account.json"
```

## 4) Run smoke test
```bash
uv run scripts/google_sheets_smoke_test.py --title test_graph_1
```

On first run, a browser auth flow opens and writes `token.json`.

Expected success output includes:
- `Smoke test passed.`
- Spreadsheet URL
- `A11: 55`
