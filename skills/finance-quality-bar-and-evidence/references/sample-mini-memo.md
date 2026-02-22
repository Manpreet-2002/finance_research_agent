# Sample Mini-Memo (High-Quality, Sector-Specific)

This is an illustrative semiconductor memo template. Numbers are examples for format quality and must be replaced with live sheet outputs before publication.

## Investment view

**Rating stance:** Constructive, with cycle-aware risk controls.

**Weighted value conclusion:** `$168/share` from `out_value_ps_weighted`, implying moderate upside versus `inp_px` at run time.

## Thesis summary

The core thesis is that the company can sustain above-market growth through a mix shift to higher-performance products while preserving structural margin gains from design leverage and scale procurement. The valuation case is not dependent on one quarter; it depends on whether utilization and product mix normalize above prior-cycle averages over the next 24 months.

## Scenario framework (read from sheet)

| Scenario | Value/share | Weight | Key assumptions |
| --- | --- | --- | --- |
| Pessimistic | `out_value_ps_pess = $118` | `inp_w_pess = 25%` | Demand correction lasts 6 quarters, gross margin below trend, slower capex digestion |
| Base | `out_value_ps_base = $172` | `inp_w_base = 50%` | Demand normalizes, mix improves gradually, operating discipline maintained |
| Optimistic | `out_value_ps_opt = $231` | `inp_w_opt = 25%` | AI/HPC demand persists, utilization strong, operating leverage expands |

Weighted valuation is formula-linked in the workbook. No off-sheet weighting is allowed.

## What must be true

1. End-market demand remains resilient enough to support the base-case growth trajectory (`inp_base_g1..inp_base_g5`).
2. Margin structure remains durable above prior-cycle median (`inp_base_m5`, `inp_base_m10`).
3. Capital intensity does not rise enough to erase FCF conversion improvements.
4. Cost of capital assumptions remain inside the sensitivity-tested range (`OUT_WACC`, `out_terminal_g`).

## Evidence map

1. SEC filings for segment mix, margin bridge, and risk disclosures. `[S1]`
2. Transcript commentary for management demand and supply-chain signals. `[S2]`
3. Peer/market data for cycle context and relative positioning. `[S3]`
4. Macro/rates context for discount-rate regime. `[S4]`

## Risks and disconfirming evidence

1. **Inventory digestion risk:** If channel inventory normalizes slower than expected, revenue growth assumptions are too high.
2. **Competitive pricing risk:** Faster competitor ramp can compress gross margin beyond base-case assumptions.
3. **Capex cycle risk:** Customer capex cuts can create a sharper utilization drop than embedded in pessimistic case.
4. **Rate regime risk:** Higher real yields can compress multiple support even if operations remain solid.

## Catalysts

1. Sequential improvement in utilization and lead times.
2. Mix improvement toward higher-margin products.
3. Revised management guidance supporting base-case margin trajectory.
4. Evidence of durable backlog quality versus short-cycle pull-ins.

## Recommendation framing

The base case is the modal outcome, but uncertainty remains two-sided. Position sizing should reflect scenario spread and catalyst timing. Maintain explicit monitoring triggers tied to the assumptions above; if two or more disconfirming indicators hit, shift probability weight from base to pessimistic and re-run sheet sensitivities.

## Citation appendix format

- `[S1]` SEC 10-K/10-Q accession IDs and section references in `Sources` tab.
- `[S2]` Earnings transcript reference with provider endpoint and timestamp.
- `[S3]` Peer set source entries with retrieval timestamps.
- `[S4]` FRED/Treasury series IDs and observation dates.
