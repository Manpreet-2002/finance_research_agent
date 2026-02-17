# Quality Bar And External Standards

This document defines the quality standard for this repo's US-stocks valuation agent.

## External standards used

1. Story-to-numbers coherence (Damodaran)
- Narrative claims must map to operating drivers, then to valuation outputs.
- Sources:
  - https://pages.stern.nyu.edu/~adamodar/
  - https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html
  - https://pages.stern.nyu.edu/~adamodar/New_Home_Page/numbers%26narrative.htm
  - https://pages.stern.nyu.edu/~adamodar/New_Home_Page/narrative/bookstory.htm

2. Disclosure-quality framing (SEC Regulation S-K)
- MD&A style: explain what changed, why, and forward implications.
- Risk factors: explicit downside channels and materiality.
- Sources:
  - https://www.law.cornell.edu/cfr/text/17/229.303
  - https://www.law.cornell.edu/cfr/text/17/229.105

3. Professional ethics and communication rigor (CFA Institute)
- Distinguish fact from judgment.
- Present limitations and uncertainty explicitly.
- Sources:
  - https://www.cfainstitute.org/en/ethics-standards/ethics

## High-quality definition for this agent

A run is high-quality only if all conditions are true:

1. Evidence completeness
- Core claims are sourced from SEC/FRED/Treasury or reconciled market/transcript/news data.
- `Sources` tab has URLs/doc IDs, timestamps, and endpoint labels.

2. Model integrity
- All valuation math is in Google Sheets formulas.
- Output claims come from `out_*` named ranges only.
- `Checks` tab passes invariant gates.

3. Assumption quality
- Each key driver has a rationale, confidence level, and disconfirming risk.
- Scenario assumptions are sector-aware and company-specific.

4. Story-to-valuation consistency
- Memo thesis and risk/catalyst statements map to assumptions and output ranges.
- "What must be true" is explicit and testable.

5. Communication quality
- Investment memo is decision-ready: thesis, scenario framing, weighted valuation, risks, catalysts, and citations.

## Scoring rubric (0-5 each)

1. Evidence quality
- 0: unsourced
- 3: partially sourced, unresolved contradictions
- 5: full provenance, contradiction resolution documented

2. Model correctness
- 0: off-sheet math or broken checks
- 3: mostly formula-linked with minor mapping gaps
- 5: fully formula-linked and all checks pass

3. Assumption rigor
- 0: arbitrary assumptions
- 3: assumptions explained but not stress-tested
- 5: evidence-backed, sector-aware, and stress-tested

4. Narrative coherence
- 0: story disconnected from model
- 3: partial linkage
- 5: full story-to-numbers linkage including disconfirming evidence

5. Decision utility
- 0: not actionable
- 3: directional only
- 5: clear recommendation, confidence range, and risk monitoring plan

## Acceptance threshold

- Minimum for publish: no category below 4, average >= 4.5.
- Hard-stop conditions: any invariant fail, missing citations for headline numbers, unresolved major source conflicts.

## Quality bar example

Low quality example:
- "Base-case value is $210/share because growth should stay strong." (no source, no sheet range, no sensitivity context)

High quality example:
- "Base-case value per share is read from `out_value_ps_base` after writing `inp_base_g1..g5`, margin path, and `inp_base_wacc`; valuation sensitivity remains within +/-11% across WACC 8.5%-9.5% and terminal growth 2.0%-3.0% in `Sensitivity`."

The high-quality version is acceptable because it identifies the model location, links assumption families, and states stress outcomes.
