# Sector Assumption Playbook (Starting Anchors)

Use this as a starting map only. Always reconcile with company filings, cycle position, and management commentary.

## General rules

1. Never hardcode sector averages into final outputs without company-specific justification.
2. Write all final assumptions into `inp_pess_*`, `inp_base_*`, `inp_opt_*` ranges.
3. Keep final valuation arithmetic inside Sheets formulas.
4. Template can be extended for sector context (extra rows/notes/charts), but core tab/range contract must remain intact.

## Sector anchors

Ranges below are practical anchors for first-pass scenarios, not hard limits.

1. Mega-cap software / platform
- Revenue growth (years 1-5): 6%-18%
- Operating margin (year 5): 25%-40%
- Terminal growth: 2.0%-3.0%
- Base WACC: 7.5%-9.5%
- Key driver: reinvestment efficiency and pricing durability

2. Semiconductors
- Revenue growth (years 1-5): 4%-20% (cycle-sensitive)
- Operating margin (year 5): 18%-35%
- Terminal growth: 2.0%-3.0%
- Base WACC: 8.0%-10.5%
- Key driver: cycle depth, capacity, and product mix

3. Banks / diversified financials
- Loan or earning-asset growth: 2%-8%
- Normalized pre-provision profitability: cycle-dependent
- Terminal growth: 1.5%-2.5%
- Base discount rate: 8.5%-11.0%
- Key driver: credit costs, capital ratios, and funding mix

4. Consumer staples
- Revenue growth (years 1-5): 2%-7%
- Operating margin (year 5): 12%-24%
- Terminal growth: 1.5%-2.5%
- Base WACC: 6.5%-8.5%
- Key driver: volume resilience and pricing power

5. Utilities
- Revenue growth (years 1-5): 1%-5%
- Operating margin (year 5): 12%-25%
- Terminal growth: 1.0%-2.0%
- Base WACC: 5.5%-7.5%
- Key driver: allowed returns and capex recovery

6. Industrials
- Revenue growth (years 1-5): 3%-10%
- Operating margin (year 5): 10%-22%
- Terminal growth: 1.5%-2.5%
- Base WACC: 7.5%-9.5%
- Key driver: backlog quality and cycle exposure

7. Biotech / pharma (single-asset or pipeline-heavy)
- Revenue growth (years 1-5): -10% to 35% (binary profile)
- Operating margin (year 5): -10% to 35%
- Terminal growth: 1.0%-2.5%
- Base WACC: 9.0%-13.0%
- Key driver: clinical and patent cliff risk

## Sector-specific examples for scenario framing

1. Software example
- Pessimistic: decelerating net retention and lower sales efficiency.
- Base: stable renewals, moderate seat expansion.
- Optimistic: cross-sell success and sustained pricing power.

2. Semiconductor example
- Pessimistic: multi-quarter inventory correction and gross margin compression.
- Base: demand normalization with moderate mix upgrade.
- Optimistic: AI/HPC demand extends cycle and lifts utilization.

3. Bank example
- Pessimistic: higher charge-offs and NIM pressure.
- Base: normalized credit costs and steady deposit beta.
- Optimistic: benign credit cycle and stronger fee growth.

## Adaptation checklist before finalizing assumptions

1. Validate cycle position against latest filings and transcripts.
2. Compare margins and growth versus peer dispersion in `Comps`.
3. Confirm `WACC > g` in all scenarios.
4. Verify scenario weights reflect uncertainty asymmetry.
