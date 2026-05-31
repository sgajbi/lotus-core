# CR-583: Transaction Cost Curve Helper Extraction

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService.get_transaction_cost_curve(...)` still owned observed transaction-cost curve
calculation helpers directly:

1. explicit cost-row versus trade-fee precedence,
2. usable evidence detection,
3. normalized security/type/currency grouping,
4. aggregate notional and fee totals,
5. average/min/max cost-bps calculations,
6. deterministic sample transaction ids,
7. cost-curve point lineage.

Those calculations are business/domain logic rather than response orchestration and made the already
large integration service harder to reason about.

## Change

Added `transaction_cost_curve.py` as a focused helper module for observed transaction-cost curve
construction:

1. `transaction_fee_amount(...)`
2. `transaction_cost_curve_key(...)`
3. `has_observed_transaction_cost_evidence(...)`
4. `build_transaction_cost_curve_point(...)`
5. `build_transaction_cost_curve_points(...)`

`IntegrationService` now delegates cost-curve evidence grouping and point construction to that
module while retaining portfolio existence checks, request fingerprinting, repository access,
cursor pagination, supportability state selection, lineage envelope, and runtime metadata.

## Impact

This moves transaction-cost curve calculation into a focused, directly tested domain helper without
changing API route shape, response fields, OpenAPI contracts, repository predicates, database
schema, wiki source, or platform contracts.

No wiki update was needed because this is an internal service-boundary extraction with no
user-facing feature, operating model, or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_transaction_cost_curve.py tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories/test_transaction_repository.py -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`
