# High-Impact Thresholds And User Question Policy

Ask the user a follow-up only when the expected decision impact is material and cannot be resolved with reliable defaults.

## Quantitative high-impact triggers

Trigger a user question if any condition is true:

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

## Question format policy

Each question must include:

1. Decision that must be made.
2. Recommended default and rationale.
3. Two to three explicit choices.
4. Effect on valuation if user accepts/rejects the recommendation.

## Example question template

- `Decision`: Base-case long-run operating margin target.
- `Recommendation`: 24% (sector median plus company moat evidence).
- `Choices`: 22%, 24%, 26%.
- `Impact`: Each 100 bps shifts weighted value per share by about 6-8% in current sensitivity table.

## Defaulting policy when user does not respond

1. Apply conservative default.
2. Mark confidence one level lower.
3. Log unresolved uncertainty in `Agent Log` and `Story` risk section.
