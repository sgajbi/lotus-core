# CR-562: Transaction Cost Evidence SQL Prefilter

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`TransactionCostCurve:v1` evidence reads fetched every transaction for the portfolio/date/as-of
window and then discarded rows without observed cost evidence in Python. On large transaction
ledgers, that forced the source-data product to materialize unrelated ledger rows before grouping
by security, transaction type, and currency.

The real evidence contract only needs transactions with positive notional and either a positive
booked `trade_fee` or at least one positive `transaction_costs.amount` row. The existing
`transaction_costs(transaction_id)` index supports an existence probe for the cost-row branch.

## Change

Moved the sparse evidence predicate into `list_transaction_cost_evidence(...)`:

1. `abs(gross_transaction_amount) > 0`
2. `trade_fee > 0`
3. `EXISTS` positive transaction-cost row by `transaction_id`

The service-level grouping and precedence rules remain unchanged: if explicit cost rows are loaded,
they still take precedence over `trade_fee`, and final positive-fee/positive-notional filtering is
still retained in the service as a safety net.

## Impact

This reduces transaction-cost source-data product read amplification without changing response
shape, paging, grouping, or evidence semantics. No database migration, API route shape, wiki source,
or platform contract changed.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_transaction_repository.py -q` - 25 passed
2. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q` - 99 passed
3. `python -m alembic heads` - `c0fbb2c3d4e5 (head)`
4. `python scripts/migration_contract_check.py --mode alembic-sql` - passed
5. touched-surface `ruff check` - passed
6. touched-surface `ruff format --check` - passed
7. `git diff --check` - passed
