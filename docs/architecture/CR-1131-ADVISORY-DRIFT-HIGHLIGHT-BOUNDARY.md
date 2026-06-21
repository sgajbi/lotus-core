# CR-1131 Advisory Drift Highlight Boundary

Date: 2026-06-21

## Scope

Query-service advisory simulation drift highlight construction in
`src/services/query_service/app/advisory_simulation/common/drift_analytics.py`.

## Finding

`_build_highlights(...)` selected largest improvements, largest deteriorations, and unmodeled
exposures for advisory drift analytics in one C-ranked helper. The logic was deterministic, but
combined three separate selector policies with DTO construction, making it harder to review ranking
and threshold behavior independently.

Radon reported:

- `_build_highlights`: `C (11)`

## Action Taken

Extracted focused helpers for:

- largest improvement detail selection,
- largest deterioration detail selection,
- maximum portfolio weight calculation,
- unmodeled exposure qualification,
- unmodeled exposure detail selection,
- highlight DTO entry construction.

Added focused test coverage proving largest-improvement ordering, deterioration filtering,
unmodeled exposure ordering, and top-limit behavior.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\advisory_simulation\test_engine_drift_analytics.py -q`
- Result: `4 passed`

Focused static proof:

- `python -m ruff check src\services\query_service\app\advisory_simulation\common\drift_analytics.py tests\unit\services\query_service\advisory_simulation\test_engine_drift_analytics.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src\services\query_service\app\advisory_simulation\common\drift_analytics.py -s`
- Result: `_build_highlights` is `A (1)`, and all functions in `drift_analytics.py` are A-ranked.

Focused maintainability proof:

- `python -m radon mi src\services\query_service\app\advisory_simulation\common\drift_analytics.py -s`
- Result: `A (40.38)`

Measured movement:

- `_build_highlights`: `C (11)` -> `A (1)`
- `drift_analytics.py` function-level complexity: no B-or-worse functions remain

## Residual Risk

This slice does not change API contracts, OpenAPI, simulation response shape, or advisory business
semantics. CR-1132 addresses the intent dependency hotspot on the same branch, and CR-1133
addresses the compliance rule-engine hotspot. Broader advisory simulation funding logic remains a
measured hotspot and should be handled as a separate focused slice.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of deterministic advisory drift highlight ranking,
- focused regression coverage for ordering and top-limit behavior,
- maintainable advisory analytics helper boundaries.

It does not claim full bank-buyable readiness for `lotus-core`.
