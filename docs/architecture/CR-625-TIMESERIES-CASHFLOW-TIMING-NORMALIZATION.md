# CR-625: Timeseries Cashflow Timing Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Position-timeseries generation normalized cashflow classification and amount values but still
bucketed beginning-of-day versus end-of-day flows by raw `cf.timing == "BOD"`. Padded or lowercase
timing evidence could therefore fall into the EOD bucket even when the source semantics were BOD.

## Change

Added `normalize_cashflow_timing(...)` to shared analytics cashflow semantics and routed
position-timeseries BOD/EOD bucket selection through it. Added focused coverage for timing
normalization in the shared helper and in daily position-timeseries generation.

## Impact

This keeps source-data timing semantics consistent with existing classification normalization before
portfolio aggregation, reconciliation, performance input generation, and reprocessing support flows
consume the generated series.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal calculation-path semantics hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_analytics_cashflow_semantics.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_position_timeseries_logic.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
