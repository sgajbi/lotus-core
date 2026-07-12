# CR-601: Position Flow Effect Conversion Guard

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Position-flow effect calculation converted `quantity` before checking whether the transaction type
used quantity. Cash-position changes use `amount`, and unknown transaction types produce zero, so
simulation and projection paths could spend Decimal conversion work on unused values.

## Change

Moved Decimal conversion behind the transaction-type branch and added focused coverage proving
cash-position and unknown transaction effects do not stringify unused quantity or amount inputs.

## Impact

This trims avoidable per-row conversion work in simulation/projection calculation paths while
preserving every existing quantity and amount effect rule. API route shape, response fields,
database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal calculation-path hardening with no
operator-facing workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_position_flow_effects.py tests/unit/services/query_service/services/test_core_snapshot_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
