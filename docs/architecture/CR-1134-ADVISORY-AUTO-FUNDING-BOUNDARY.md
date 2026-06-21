# CR-1134 Advisory Auto-Funding Boundary

Date: 2026-06-21

## Scope

Query-service advisory simulation auto-FX funding plan construction in
`src/services/query_service/app/advisory_simulation/advisory/funding.py`.

## Finding

`build_auto_funding_plan(...)` mixed proposal BUY grouping, per-currency funding need calculation,
cash-ledger candidate selection, missing-FX diagnostics, insufficient-cash diagnostics, generated
FX intent creation, portfolio mutation, and funding-plan evidence updates in one C-ranked function.
`funding_priority_currencies(...)` also carried branch-heavy base-only versus multi-currency
candidate ordering.

Radon reported:

- `build_auto_funding_plan`: `C (20)`
- `funding_priority_currencies`: `B (6)`

## Action Taken

Extracted focused helpers for:

- funding-policy enablement,
- BUY grouping by notional currency,
- funding priority candidate construction,
- per-target funding need and plan-entry construction,
- candidate FX selection and smallest-deficit tracking,
- missing-FX pending-review versus hard-block posture,
- insufficient funding diagnostics,
- generated FX intent construction and portfolio mutation.

The public `build_auto_funding_plan(...)` return tuple and generated FX/funding-plan semantics remain
unchanged.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\advisory_simulation\test_engine_advisory_proposal_simulation.py -q`
- Result: `29 passed`

Focused static proof:

- `python -m ruff check src\services\query_service\app\advisory_simulation\advisory\funding.py tests\unit\services\query_service\advisory_simulation\test_engine_advisory_proposal_simulation.py`
- Result: passed

Focused type proof:

- `make typecheck`
- Result: passed

Focused complexity proof:

- `python -m radon cc src\services\query_service\app\advisory_simulation\advisory\funding.py -s`
- Result: `build_auto_funding_plan` is `A (4)`, `funding_priority_currencies` is `A (2)`, and
  all functions/classes in `funding.py` are A-ranked.

Focused maintainability proof:

- `python -m radon mi src\services\query_service\app\advisory_simulation\advisory\funding.py -s`
- Result: `A (29.68)`

Package-level hotspot proof:

- `python -m radon cc src\services\query_service\app\advisory_simulation -s | Select-String -Pattern " - [C-F] \("`
- Result: no C-or-worse advisory simulation functions reported.

Measured movement:

- `build_auto_funding_plan`: `C (20)` -> `A (4)`
- `funding_priority_currencies`: `B (6)` -> `A (2)`
- `funding.py` function-level complexity: no B-or-worse functions remain

## Residual Risk

This slice does not change API contracts, OpenAPI, advisory simulation response shape, generated FX
intent semantics, or advisory funding policy. The broader advisory simulation package should
continue to be monitored through the existing complexity and maintainability gates, but this slice
closes the measured CR-1131 through CR-1133 funding hotspot follow-up.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of advisory funding selection and failure posture,
- deterministic audit evidence for generated FX funding behavior,
- separation of missing-FX supportability from insufficient-cash supportability.

It does not claim full bank-buyable readiness for `lotus-core`.
