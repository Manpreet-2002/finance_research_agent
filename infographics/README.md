# Infographics Environment (Vega-Lite + ECharts)

This folder is a dedicated local runtime to generate infographic PNGs with:
- Vega-Lite
- ECharts
- Playwright (headless Chromium for deterministic rendering)

## Why this setup
- One runtime for both libraries.
- PNG output fidelity is consistent with browser rendering.
- Avoids ad-hoc notebook scripting for every chart.

## Prerequisites
- Node.js `>=20.11.0`
- npm `>=10`

## Setup
```bash
cd infographics
npm install
npm run install:browsers
npm run doctor
```

## Smoke test
```bash
cd infographics
npm run smoke
```

Expected output:
- `artifacts/infographics/env_smoke/vega_echarts_smoke.png`

## MCD Client-Ready PoC (both libraries)
```bash
cd infographics
npm run mcd:poc
```

Outputs:
- `artifacts/infographics/mcd_poc_client_ready/png/vega_lite/*.png`
- `artifacts/infographics/mcd_poc_client_ready/png/echarts/*.png`
- `artifacts/infographics/mcd_poc_client_ready/sources.md`
- `artifacts/infographics/mcd_poc_client_ready/comparison.md`

## Recommended production flow
1. Build chart data JSON from run artifacts.
2. Build chart specs/options (Vega-Lite + ECharts) from that JSON.
3. Render via Playwright and export PNGs to `artifacts/infographics/<run_id>/`.

Keep citations in a separate source file (not drawn onto charts).
