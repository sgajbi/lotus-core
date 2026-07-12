# CR-1140 Analytics Position Snapshot-Epoch Filter Boundary

Date: 2026-06-22

## Scope

Position snapshot-epoch filtering in
`src/services/query_service/app/repositories/analytics_timeseries_repository.py`.

## Finding

`AnalyticsTimeseriesRepository.get_position_snapshot_epoch(...)` owned max-epoch selection plus
security scope filtering, position-ID scope filtering, instrument dimension filters, and
unsupported scope posture in one B-ranked repository method. This method establishes the snapshot
epoch used by analytics timeseries reads, so its filtering policy needs to remain directly
reviewable and aligned with page-read filtering.

Radon reported:

- `AnalyticsTimeseriesRepository.get_position_snapshot_epoch`: `B (9)`

## Action Taken

Extracted focused helpers for:

- trimmed position-timeseries security ID expression reuse,
- position-timeseries security-scope filtering,
- position-timeseries position-ID scope filtering,
- instrument dimension predicate construction.

Added direct unit coverage proving invalid position-ID scopes return snapshot epoch `0` without a
DB query.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\repositories\test_analytics_timeseries_repository.py -q`
- Result: `8 passed`

Focused static proof:

- `python -m ruff check src/services/query_service/app/repositories/analytics_timeseries_repository.py tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py`
- Result: passed

Focused format proof:

- `python -m ruff format --check src/services/query_service/app/repositories/analytics_timeseries_repository.py tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/query_service/app/repositories/analytics_timeseries_repository.py -s --exclude "*/build/*"`
- Result: `AnalyticsTimeseriesRepository.get_position_snapshot_epoch` is `A (5)`, and every
  function/class in `analytics_timeseries_repository.py` is A-ranked.

Measured movement:

- `AnalyticsTimeseriesRepository.get_position_snapshot_epoch`: `B (9)` -> `A (5)`
- `analytics_timeseries_repository.py`: no B-or-worse functions/classes remain

## Residual Risk

This slice does not change analytics timeseries API contracts, max-epoch semantics, date-window
filtering, instrument joins, or downstream analytics service behavior. Broader service-level
analytics orchestration remains covered by the existing analytics service tests and should be
handled separately if measured risk points there.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of snapshot-epoch scope policy,
- consistency with analytics page-filter posture,
- deterministic proof for unsupported position-ID scope behavior.

It does not claim full bank-buyable readiness for `lotus-core`.
