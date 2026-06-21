# CR-1127 Holdings Data-Quality Policy Boundary

Date: 2026-06-21

## Scope

Query-service HoldingsAsOf response supportability policy in
`src/services/query_service/app/services/position_holdings.py`.

## Finding

`holdings_data_quality_status(...)` was an API-facing classifier for the governed
`HoldingsAsOf:v1` source product, but it combined empty holdings, missing reprocessing state,
non-current reprocessing state, market-price freshness, history-supplement, and final COMPLETE
classification in one branch-heavy function.

Radon reported:

- `holdings_data_quality_status`: `C (12)`

The behavior is contract-relevant because downstream consumers use Core's data-quality posture to
decide whether HoldingsAsOf evidence is complete, partial, stale, or unknown.

## Action Taken

Extracted focused helpers for:

- reprocessing status normalization,
- unknown-state detection,
- non-current-state detection,
- stale market-price evidence detection,
- reprocessing-derived data-quality classification.

The public `holdings_data_quality_status(...)` API, response status vocabulary, route behavior, and
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
- Result: `holdings_data_quality_status` is `A (4)`, and extracted helper functions are A-ranked.

Focused maintainability proof:

- `python -m radon mi src\services\query_service\app\services\position_holdings.py -s`
- Result after CR-1128 on the same branch: `A (26.17)`

Measured movement:

- `holdings_data_quality_status`: `C (12)` -> `A (4)`

## Residual Risk

This slice does not change API contracts, OpenAPI, persistence, or cross-app integration behavior.
`merge_snapshot_and_history_position_rows` remains B-ranked and should be addressed separately with
focused API-facing proof.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of a source-owned API supportability classifier,
- explicit data-quality decision boundaries for HoldingsAsOf evidence,
- regression coverage for non-current state, stale market-price evidence, and current/fresh
  COMPLETE classification.

It does not claim full bank-buyable readiness for `lotus-core`.
