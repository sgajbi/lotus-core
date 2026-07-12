# CR-1139 Analytics Position Timeseries Page-Filter Boundary

Date: 2026-06-22

## Scope

Position timeseries page filtering in
`src/services/query_service/app/repositories/analytics_timeseries_repository.py`.

## Finding

`AnalyticsTimeseriesRepository.list_position_timeseries_rows(...)` owned ranked position-timeseries
projection plus cursor filtering, security scope filtering, position-ID scope filtering, dimension
filters, ordering, and page-size handling in one C-ranked repository method. This read path feeds
analytics timeseries APIs, so pagination and scope predicates need to remain easy to inspect.

Radon reported:

- `AnalyticsTimeseriesRepository.list_position_timeseries_rows`: `C (11)`

## Action Taken

Extracted focused helpers for:

- cursor/keyset predicate construction,
- dimension filter predicate construction,
- optional predicate application,
- security-scope filtering,
- position-ID scope filtering.

Added direct unit coverage proving invalid position-ID scopes return no rows without a DB query.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\repositories\test_analytics_timeseries_repository.py -q`
- Result: `7 passed`

Focused static proof:

- `python -m ruff check src/services/query_service/app/repositories/analytics_timeseries_repository.py tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py`
- Result: passed

Focused format proof:

- `python -m ruff format --check src/services/query_service/app/repositories/analytics_timeseries_repository.py tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/query_service/app/repositories/analytics_timeseries_repository.py -s --exclude "*/build/*"`
- Result: `AnalyticsTimeseriesRepository.list_position_timeseries_rows` is `A (5)`.

Measured movement:

- `AnalyticsTimeseriesRepository.list_position_timeseries_rows`: `C (11)` -> `A (5)`

## Residual Risk

This slice does not change analytics timeseries API contracts, ranked row projection, quantity
matching, snapshot-epoch semantics, ordering, or pagination size. The adjacent
`get_position_snapshot_epoch(...)` helper remains B-ranked and should be handled separately if it is
the next measured analytics repository hotspot.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of analytics timeseries page filters,
- deterministic proof for invalid position-ID scope posture,
- lower branch complexity in a high-use portfolio analytics repository path.

It does not claim full bank-buyable readiness for `lotus-core`.
