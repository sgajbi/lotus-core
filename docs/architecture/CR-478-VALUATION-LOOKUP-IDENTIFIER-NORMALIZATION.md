# CR-478: Valuation Lookup Identifier Normalization

Date: 2026-05-28

## Scope

Shared valuation repository caller-identifier lookup boundaries for portfolio lookup, batched
portfolio lookup, position-history lookback, and valuation-job status update.

## Finding

The shared valuation repository had already normalized FX, instrument, and market-price lookup
inputs, but several adjacent caller-identifier paths still compared raw portfolio/security values:
single portfolio lookup, batched portfolio lookup, last position-history read before valuation, and
valuation-job status update.

Padded caller values or historical padded rows could make an existing portfolio look missing, miss
the last known position before valuation, or fail to close a processing valuation job. Those issues
can create false missing-data posture, stale valuation jobs, and incorrect or delayed valuation
evidence for downstream analytics.

## Change

Updated `ValuationRepositoryBase` so:

1. repository-local generic identifier trimming is available through `_normalize_identifier(...)`,
2. `get_portfolio(...)` trims caller and persisted portfolio IDs,
3. `get_portfolios_by_ids(...)` trims batched portfolio IDs and drops blanks before querying,
4. `get_last_position_history_before_date(...)` trims caller and persisted portfolio/security IDs,
5. `update_job_status(...)` trims caller and persisted portfolio/security IDs before matching the
   processing valuation job.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py -q`
2. `python -m pytest tests/unit/services/calculators/position_valuation_calculator -q`
3. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py`
6. `git diff --check`

Results:

1. Focused valuation repository proof: `15 passed`
2. Position valuation calculator unit pack: `39 passed`
3. Portfolio-common unit pack: `486 passed`
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required.
Valuation caller-identifier lookup boundaries now use trim-normalized identifier semantics where
they directly affect portfolio lookup, position-history lookup, and valuation-job closure.
