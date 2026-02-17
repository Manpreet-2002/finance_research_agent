# Tests (V1)

Test suites are organized by type:
- `tests/unit/`: pure logic and schema checks
- `tests/integration/`: API/tool and Sheets engine integration
- `tests/evals/`: benchmark regression and invariant evaluations

Priority invariants from PRD:
- WACC bounds and `WACC > g`
- DCF identity/bridge checks
- output contract completeness
- citation presence for memo numeric claims
