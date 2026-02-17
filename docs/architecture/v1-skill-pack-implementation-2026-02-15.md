# V1 Skill Pack Implementation (February 15, 2026)

This document records the Anthropic-style skill pack added for the Phase V1 finance research workflow.

## Scope implemented

- Added 14 phase-aligned skills under `skills/`.
- Added `agents/openai.yaml` metadata for each skill.
- Added shared quality/evidence references with:
  - quality rubric and external standards
  - source-priority and contradiction policy
  - high-impact question thresholds
  - sector-specific assumption anchors
  - full sample mini-memo
  - sample in-sheet log entries

## Skill index

1. `skills/ticker-intake-and-mandate`
2. `skills/sec-filings-and-xbrl-extraction`
3. `skills/market-and-fundamentals-harvest`
4. `skills/rates-and-macro-context`
5. `skills/transcript-and-guidance-analysis`
6. `skills/corporate-actions-and-cap-table`
7. `skills/peer-set-and-competitive-analysis`
8. `skills/assumption-engine-pess-base-opt`
9. `skills/sheets-dcf-executor`
10. `skills/sensitivity-engine`
11. `skills/story-to-valuation-linker`
12. `skills/citation-and-consistency-auditor`
13. `skills/memo-composer-ib-style`
14. `skills/publish-and-logbook-closeout`

Shared foundation:

- `skills/finance-quality-bar-and-evidence`

## Shared quality references

Located in `skills/finance-quality-bar-and-evidence/references/`:

1. `quality-bar-and-standards.md`
2. `source-priority-and-contradiction-policy.md`
3. `high-impact-thresholds-and-question-policy.md`
4. `sector-assumption-playbook.md`
5. `google-sheets-execution-policy.md`
6. `sample-mini-memo.md`
7. `sample-sheet-log-entries.md`

## Key operating constraints encoded in skills

1. All Google Sheets operations are API-driven.
2. The local template file is not transformed.
3. Valuation math is formula-driven inside Google Sheets only.
4. Material claims require citation and range grounding.

## Backend wiring update

`backend/app/skills/catalog.py` now includes `skill_path` for each phase-v1 `SkillSpec`, linking routing metadata to concrete skill artifact folders.

## Anthropic skill references used

1. https://docs.claude.com/en/docs/agents-and-tools/agent-skills
2. https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
3. https://docs.claude.com/en/docs/claude-code/slash-commands
4. https://platform.claude.com/docs/en/build-with-claude/skills-guide
5. https://docs.claude.com/en/api/agent-sdk/skills

## External standards references used for quality bar

1. Damodaran story-to-numbers and valuation datasets:
- https://pages.stern.nyu.edu/~adamodar/
- https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html
- https://pages.stern.nyu.edu/~adamodar/New_Home_Page/numbers%26narrative.htm
- https://pages.stern.nyu.edu/~adamodar/New_Home_Page/narrative/bookstory.htm

2. SEC disclosure standards:
- https://www.law.cornell.edu/cfr/text/17/229.303
- https://www.law.cornell.edu/cfr/text/17/229.105

3. CFA ethics and communication standards:
- https://www.cfainstitute.org/en/ethics-standards/ethics
