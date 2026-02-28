# Frontend (V1)

Next.js dashboard for ticker submission and valuation execution history.

## Features
- submit stock ticker to backend (`POST /api/v1/executions`)
- live execution history table (`GET /api/v1/executions`)
- direct links to Google Sheets and memo PDF API endpoint
- explicit UTC timestamps across the UI

## Local run
```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

Default app URL: `http://localhost:3000`.
