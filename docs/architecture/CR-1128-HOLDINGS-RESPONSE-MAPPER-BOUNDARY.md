# CR-1128 Holdings Response Mapper Boundary

Date: 2026-06-21

## Scope

Query-service HoldingsAsOf response row mapping in
`src/services/query_service/app/services/position_holdings.py`.

## Finding

`position_response_data(...)` was the API-facing mapper from snapshot/history row, instrument row,
position state, and valuation evidence into the `Position` DTO. It preserved the correct response
shape, but the function carried repeated inline conditional field selection for snapshot/history
date, optional instrument attributes, and optional reprocessing state.

Radon reported:

- `position_response_data`: `C (12)`

## Action Taken

Extracted focused helpers for:

- snapshot/history row date selection,
- optional instrument field selection with the existing `N/A` instrument-name fallback,
- optional position-state status selection.

The public mapper signature, `Position` DTO fields, fallback values, response route behavior, and
`HoldingsAsOf:v1` contract shape remain unchanged.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_holdings_response.py -q`
- Result: `34 passed`

Focused static proof:

- `python -m ruff check src\services\query_service\app\services\position_holdings.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_holdings_response.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src\services\query_service\app\services\position_holdings.py -s`
- Result: `position_response_data` is `A (1)`, and extracted helper functions are A-ranked.

Focused maintainability proof:

- `python -m radon mi src\services\query_service\app\services\position_holdings.py -s`
- Result: `A (26.17)`

Measured movement:

- `position_response_data`: `C (12)` -> `A (1)`
- `position_holdings.py` maintainability: `A (25.47)` -> `A (26.17)` after CR-1128

## Residual Risk

This slice does not change API contracts, OpenAPI, persistence, or cross-app integration behavior.
`merge_snapshot_and_history_position_rows` remains B-ranked and should be addressed separately
because it owns snapshot/history precedence and basis-reconciliation policy.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of the HoldingsAsOf DTO mapping boundary,
- explicit fallback policy for optional instrument and state fields,
- confidence that API-facing row mapping remains covered by focused tests.

It does not claim full bank-buyable readiness for `lotus-core`.
