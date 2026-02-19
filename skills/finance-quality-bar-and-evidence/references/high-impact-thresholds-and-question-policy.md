# High-Impact Thresholds And Defaulting Policy

No human-in-the-loop is enabled for this runtime. Do not ask follow-up questions. When uncertainty is high-impact, apply conservative defaults, widen scenario dispersion where appropriate, and downgrade confidence.

## Quantitative high-impact triggers

Treat uncertainty as high-impact if any condition is true:

1. Valuation dispersion
- `max(out_value_ps_*) - min(out_value_ps_*)` exceeds 35% of base case.

2. Weight sensitivity
- Reweighting plausible scenarios changes `out_value_ps_weighted` by >= 12%.

3. WACC uncertainty
- Reasonable WACC range width > 150 bps and changes weighted value by >= 10%.

4. Terminal growth uncertainty
- Plausible terminal growth range width > 100 bps and changes weighted value by >= 8%.

5. Share count uncertainty
- Diluted share estimate uncertainty > 3% from conflicting buyback/dilution evidence.

6. Contradiction unresolved
- High-priority and lower-priority sources conflict beyond thresholds and no authoritative tie-breaker exists.

## Qualitative high-impact triggers

1. Material business model transition (e.g., hardware to recurring software revenue).
2. Major regulatory or litigation overhang with binary outcomes.
3. Balance-sheet risk that can alter survival probability or refinancing assumptions.

## Required handling policy

For every triggered high-impact uncertainty:

1. Apply a conservative default anchored to source hierarchy and sector medians.
2. Document rationale and confidence downgrade in `log_assumptions_table`.
3. Reflect uncertainty in scenarios (weights, growth, margin, or discount-rate spread).
4. Ensure `Sensitivity` includes stress points covering the uncertainty range.
5. Record contradiction resolution in `log_actions_table` when source conflict exists.

## Example default template

- `Decision`: Base-case long-run operating margin target.
- `Default`: 24% (conservative vs recent run-rate, anchored to sector median).
- `Rationale`: Protect against cycle compression and execution variance.
- `Impact`: Each 100 bps shifts weighted value per share by about 6-8% in current sensitivity table.
- `Confidence`: Medium (conflicting guidance + macro uncertainty).

## Defaulting policy

1. Apply conservative default.
2. Mark confidence one level lower.
3. Log unresolved uncertainty in `Agent Log` and `Story` risk section.
