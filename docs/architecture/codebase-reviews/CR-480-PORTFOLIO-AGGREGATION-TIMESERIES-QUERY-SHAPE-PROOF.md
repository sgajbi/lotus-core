# CR-480: Portfolio Aggregation Timeseries Query-Shape Proof

Date: 2026-05-28

## Scope

Portfolio aggregation repository tests for shared timeseries position-timeseries lookup query shape.

## Finding

GitHub Feature Lane run `26561143644` failed in the warning gate because
`tests/unit/services/portfolio_aggregation_service/repositories/test_timeseries_repository.py`
still characterized the pre-hardening query shape. The shared timeseries repository now partitions
and joins position timeseries by trimmed security IDs and filters by trimmed portfolio IDs, but the
portfolio aggregation test still expected raw `position_timeseries.security_id` partitioning.

That stale test blocked the branch even though the production query hardening was intentional and
covered by the timeseries generator repository tests.

## Change

Updated the portfolio aggregation timeseries repository test to assert:

1. partitioning by `trim(position_timeseries.security_id)`,
2. portfolio filtering by `trim(position_timeseries.portfolio_id)`,
3. join-back on trimmed portfolio/security identifiers,
4. the existing date, epoch, and latest-row guard behavior.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/portfolio_aggregation_service/repositories/test_timeseries_repository.py -q`
2. `python -m pytest tests/unit/services/portfolio_aggregation_service -q`
3. `python -m ruff check tests/unit/services/portfolio_aggregation_service/repositories/test_timeseries_repository.py`
4. `python -m ruff format --check tests/unit/services/portfolio_aggregation_service/repositories/test_timeseries_repository.py`
5. `make warning-gate`
6. `git diff --check`

Results:

1. Focused portfolio aggregation repository proof: `7 passed`
2. Portfolio aggregation unit pack: `21 passed`
3. Touched-surface ruff: passed
4. Touched-surface format check: passed
5. Warning gate: passed
6. Diff hygiene: passed

## Closure

Status: Hardened.

No production code, route shape, database migration, wiki source, or platform contract change was
required. The portfolio aggregation characterization now matches the shared normalized timeseries
query contract and closes the observed GitHub Feature Lane failure.
