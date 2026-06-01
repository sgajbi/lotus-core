# CR-703: Support Overview Evidence Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`get_support_overview(...)` already fanned out the main support-health reads, but after that
fan-out it read latest reconciliation evidence before starting booked transaction and booked
snapshot evidence. Those evidence chains are independent once the latest control stage and latest
business date are known, so the endpoint paid avoidable sequential latency on an operations
dashboard hot path.

## Change

Added focused private helpers for latest reconciliation evidence and latest booked-date evidence,
then routed `get_support_overview(...)` through a second `asyncio.gather(...)` phase. The
reconciliation chain still preserves the dependency from latest control stage to latest
reconciliation run to finding summary, and booked-date reads still remain suppressed when there is
no latest business date.

Added focused operations-service coverage that proves reconciliation evidence and booked-date
evidence start concurrently.

## Impact

This reduces operations support overview latency for portfolios with reconciliation controls and a
booked business date while preserving portfolio validation, invalid-portfolio fan-out suppression,
reconciliation evidence semantics, no-business-date behavior, response contracts, database schema,
wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused operations-service support-overview proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
