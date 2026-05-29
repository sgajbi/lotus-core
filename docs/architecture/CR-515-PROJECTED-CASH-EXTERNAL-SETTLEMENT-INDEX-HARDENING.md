# CR-515: Projected Cash External Settlement Index Hardening

Date: 2026-05-29

## Scope

Cashflow projection reads for future external cash movements.

## Finding

`CashflowRepository.get_projected_settlement_cashflow_series` and the projected evidence timestamp
query read future settlement-dated external movements by portfolio, settlement-date window, booked
transaction date, and transaction type limited to `DEPOSIT` and `WITHDRAWAL`.

CR-493 added the general `(portfolio_id, settlement_date, id)` index and removed the previous
`date(settlement_date)` predicate. That general index remains useful, but the projection hot path
can still scan transaction families that are irrelevant to external liquidity projection. For large
private-banking books, external cash movement projection should use a smaller index scoped to the
actual supported movement classes.

## Change

1. Added `ix_txn_projected_cash_external_port_settle_txn_date_id` on
   `(portfolio_id, settlement_date, transaction_date, id)`.
2. Scoped the index with a partial predicate:
   `transaction_type IN ('DEPOSIT', 'WITHDRAWAL') AND settlement_date IS NOT NULL`.
3. Added Alembic migration `c0f0a1b2c3d4_perf_add_projected_cash_external_index.py`.
4. Added model metadata proof that the partial index remains aligned to the cashflow projection
   query contract.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_query_cashflow_repository.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_query_cashflow_repository.py alembic/versions/c0f0a1b2c3d4_perf_add_projected_cash_external_index.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_query_cashflow_repository.py alembic/versions/c0f0a1b2c3d4_perf_add_projected_cash_external_index.py`
7. `git diff --check`

Results:

1. Passed: 24 tests.
2. Passed: 220 tests.
3. Passed: single head `c0f0a1b2c3d4`.
4. Passed.
5. Passed.
6. Passed.
7. Passed.

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. This is index hardening
for an existing cashflow projection read path.
