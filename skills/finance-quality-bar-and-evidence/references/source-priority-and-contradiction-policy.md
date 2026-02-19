# Source Priority And Contradiction Policy

## Source trust order (V1 policy)

1. SEC / FRED / Treasury
2. Alpha Vantage
3. Finnhub
4. Web/news search

If two sources disagree, use the higher-priority source unless data freshness or schema mismatch makes it invalid.

## Field-level source preference

1. Filing-accounting facts (`revenue`, `EBIT`, `tax`, shares in filing period)
- Primary: SEC XBRL/companyfacts
- Secondary: Finnhub reported financials

2. Risk-free and macro series
- Primary: FRED/Treasury
- Secondary: none

3. Transcripts and guidance snippets
- Primary: Alpha Vantage transcript payload
- Secondary: earnings press release / filing text excerpts

4. Corporate actions (splits/dividends/buybacks headlines)
- Primary: Alpha Vantage corporate actions
- Secondary: SEC filing text and issuer releases

5. Peer and sector mapping
- Primary: Finnhub peers/profile
- Secondary: web-confirmed issuer disclosures

6. Event/catalyst context
- Primary: Tavily/web retrieval with source URLs
- Secondary: market data provider news feeds

## Contradiction detection protocol

Flag a contradiction if any condition is true:

1. Same metric, same period, absolute difference > 5% and > materiality threshold.
2. Directional mismatch for guidance (one source says increase, another says decrease).
3. Timestamp mismatch where stale source is older than 90 days for high-volatility fields.

## Resolution procedure

1. Normalize units and period first.
2. Prefer higher-priority source.
3. If unresolved, apply conservative defaults and downgrade confidence using the high-impact thresholds policy.
4. Log final decision in `Checks` and `Agent Log` with:
- metric
- compared sources
- delta
- chosen source
- rationale
- confidence

## Confidence labels

- High: trusted source, low discrepancy, current timestamp
- Medium: trusted source but stale/partial detail
- Low: unresolved conflict or fallback source only

## Required log templates

Action ledger summary string:
- `VALIDATE | contradiction_check | metric=<metric> period=<period> delta=<delta_pct> chosen=<source> confidence=<label>`

Assumption journal method string:
- `source_priority_resolution(<metric>, <period>, <source_a>, <source_b>)`
