# CR-677: Simulation Projection Baseline Change Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`SimulationService.get_projected_positions(...)` resolved the simulation session, then loaded the
portfolio baseline positions before reading the session change set. Baseline holdings and pending
simulation changes are independent once the active session is known; they are only combined later
when proposed quantities are calculated.

## Change

The service now reads latest baseline snapshot positions and session changes with
`asyncio.gather(...)`. If no snapshot baseline exists, the existing position-history fallback still
runs, and the already loaded change set is reused for projection assembly.

Added service coverage that would deadlock under sequential execution, proving the baseline and
change reads are started concurrently.

## Impact

This reduces projected-position simulation latency while preserving session validation, snapshot
preference, history fallback behavior, instrument enrichment, quantity-effect rules, response
contracts, database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused simulation service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
