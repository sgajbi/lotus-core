# CR-630: Mandate Rebalance Band Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Discretionary mandate binding payload assembly normalized most source-data numeric evidence through
shared integration helpers, but mandate rebalance-band metadata still parsed optional
`cash_reserve_weight` after only an `is not None` check. Blank source metadata could therefore raise
a low-level required-decimal error while assembling a product-facing source-data response.

The default rebalance band also defaulted only when the key was absent, not when source metadata
provided a blank value.

## Change

Routed discretionary mandate rebalance-band metadata through `as_optional_decimal(...)`, preserving
strict required behavior elsewhere while treating sparse optional band evidence as absent. Blank
`default_band` evidence now falls back to the existing zero default.

Added focused discretionary mandate binding coverage for blank default-band and cash-reserve values.

## Impact

This keeps mandate source-data evidence deterministic for advisory, DPM readiness, gateway
integration, and client-readiness consumers while preserving response shape, lineage, supportability
state, and strict required-field behavior for mandatory values.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal source-data payload normalization hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
