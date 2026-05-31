# CR-584: Transaction Cost Positive Evidence Index

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`TransactionCostCurve:v1` reads now prefilter transaction evidence in SQL using the real sparse
evidence contract introduced by CR-562:

1. positive gross transaction notional,
2. positive booked `transactions.trade_fee`, or
3. at least one positive `transaction_costs.amount` row for the transaction.

The cost-row branch uses an `EXISTS` probe on `transaction_costs.transaction_id` plus
`transaction_costs.amount > 0`. The broad FK-support index on `transaction_costs(transaction_id)`
is still needed for relationship joins and deletes, but it does not encode the sparse positive-cost
evidence predicate used by the source-data product hot path.

## Change

Added `ix_txn_costs_positive_txn_id` as a PostgreSQL partial index on
`transaction_costs(transaction_id)` where `amount > 0`.

The index is declared in SQLAlchemy model metadata and introduced through Alembic migration
`c0fdd4e5f6a8`. The transaction-cost curve repository query shape is unchanged and continues to
own the real predicate:

1. portfolio/date/as-of fencing on `transactions`,
2. positive notional,
3. positive aggregate trade fee or positive explicit cost-row evidence,
4. optional normalized security and transaction-type filters,
5. deterministic grouping order.

## Impact

This narrows the cost-row existence probe to sparse positive cost evidence without changing API
route shape, response fields, OpenAPI contracts, repository semantics, wiki source, or platform
contracts.

No wiki update was needed because this is an internal database performance hardening slice with no
operator-facing workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_transaction_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python scripts/test_manifest.py --suite unit-db --quiet`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`
