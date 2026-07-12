# CR-638: Transaction Cost Curve Paged Point Build

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The transaction-cost curve source-data product fetched the filtered transaction-cost evidence rows
and then built every eligible curve-point DTO before applying the requested page token and page
size. Broad evidence windows with many security/type/currency groups therefore paid DTO assembly,
cost-bps calculation, observed-date reduction, and sample-id sorting for groups outside the
returned page.

## Change

Added a transaction-cost curve page builder that groups usable observations once, keeps the full
eligible key set for missing-security and pagination semantics, and builds
`TransactionCostCurvePoint` records only for the requested page slice.

## Impact

This reduces response-assembly CPU and object allocation for broad transaction-cost evidence
windows while preserving grouping keys, minimum-observation filtering, deterministic page-token
ordering, missing requested-security detection, supportability state, latest evidence timestamp
handling, lineage, and response shape.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal source-data product response-assembly
performance hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_transaction_cost_curve.py tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
