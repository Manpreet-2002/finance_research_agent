# V1 data service: fields and sources

This document defines the initial data contract for the backend tool layer and where each field comes from.

## Input/output diagram
```mermaid
flowchart LR
  subgraph Inputs
    T[Ticker\n(e.g., AAPL)]
    C[Provider config + API keys\n(.env)]
  end

  subgraph Providers
    F1[Finnhub\nstock/profile2]
    F2[Finnhub\nstock/metric]
    F3[Finnhub\nstock/financials-reported]
    F4[Finnhub\nquote]
    W1[Tavily\nsearch]
    S1[SEC EDGAR/XBRL\ncompany_tickers + companyfacts]
    R[FRED\nseries/observations]
  end

  DS[DataService.build_canonical_dataset]

  subgraph Outputs
    O1[CanonicalValuationDataset\n- fundamentals\n- market\n- rates\n- news\n- citations]
    O2[Sheets named-range payload\n(inp_*)]
  end

  T --> DS
  C --> DS
  DS --> F1
  DS --> F2
  DS --> F3
  DS --> F4
  DS --> W1
  DS --> S1
  DS --> R
  F1 --> DS
  F2 --> DS
  F3 --> DS
  F4 --> DS
  W1 --> DS
  S1 --> DS
  R --> DS
  DS --> O1
  O1 --> O2
```

Current V1 decision: Finnhub is primary for fundamentals/market, Tavily is primary for web/news evidence, SEC adapter is available for filing-backed fundamentals, and rates remain FRED.

## Canonical outputs consumed by the model engine
- Fundamentals (`CompanyFundamentals`)
- Market snapshot (`MarketSnapshot`)
- Rates snapshot (`RatesSnapshot`)
- News list (`NewsItem[]`)
- Source citations (`DataSourceCitation[]`)
- Complete sheets payload (`inp_*`) for the DCF template contract

## Fundamentals fields
Default provider: `finnhub`

- `company_name`, `currency`:
  - Finnhub endpoint: `stock/profile2`
- `revenue_ttm`, `ebit_ttm`, `tax_rate_ttm`, `da_ttm`, `capex_ttm`, `delta_nwc_ttm`:
  - Finnhub endpoint: `stock/financials-reported` (quarterly; aggregated across recent periods)
- `rd_ttm`, `rent_ttm`:
  - Finnhub endpoint: `stock/financials-reported` income statement concepts (when available)
- `cash`, `debt`, `basic_shares`:
  - Finnhub endpoint: `stock/financials-reported` balance sheet concepts
  - fallback to `stock/metric` (`metric=all`) and profile shares

Implemented optional alternative:
- `sec_edgar` fundamentals adapter (`SecEdgarFundamentalsClient`) for SEC filing-backed ingestion.

## Market fields
Default provider: `finnhub`

- `price`:
  - Finnhub endpoint: `quote`
- `beta`, `shares_outstanding`:
  - Finnhub endpoint: `stock/metric` + profile fallback
- `market_cap`:
  - Finnhub endpoint: `stock/profile2`

## Rates fields
Default provider: `fred`

- `risk_free_rate`:
  - FRED endpoint: `series/observations`
  - Default series: `DGS10`
  - Values converted from percent to decimal for sheet inputs.
- `equity_risk_premium`, `cost_of_debt`, `debt_weight`:
  - V1 defaults from environment variables.

## News fields
Default provider: `tavily`

- `headline`, `publisher`, `published_at_utc`, `url`, `summary`:
  - Tavily endpoint: `search`
  - Query is generated from ticker + catalyst/risk terms and normalized into `NewsItem`.
  - Optional fallback provider remains `finnhub` (`company-news`) when configured.

## Provider switching model
Providers are selected via env vars and assembled by `build_data_service(...)` in `backend/app/tools/provider_factory.py`.

- `FUNDAMENTALS_PROVIDER` (`finnhub`, `sec_edgar`)
- `MARKET_DATA_PROVIDER` (`finnhub`, `placeholder`)
- `NEWS_PROVIDER` (`tavily`, `finnhub`, `placeholder`)
- `RATES_PROVIDER` (`fred`, `static`)

## DCF input completeness behavior
`CanonicalValuationDataset.to_sheets_named_ranges()` returns all required template inputs (`inp_*`) by combining:
- fetched market/fundamental/rates values
- model defaults from environment configuration
- deterministic fallbacks where provider data is missing (for example `inp_tax_ttm` fallback to `inp_tax_norm`, `inp_dNWC_ttm` fallback to 0)

Unit normalization applied at the sheet-mapping boundary:
- monetary inputs written to the template are normalized to `USD ($mm)`
- share count inputs are normalized to `mm` shares
