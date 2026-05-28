# CR-493: Settlement Cashflow Query Index Hardening

Date: 2026-05-28

## Scope

Projected settlement cashflow reads and transaction settlement-date index posture.

## Finding

Projected settlement cashflow APIs select future external `DEPOSIT` and `WITHDRAWAL` movements by
portfolio and settlement-date window. The query filtered with `date(transactions.settlement_date)`
and the transaction table had no portfolio/settlement-date composite index. That left projected
cashflow windows and settlement-date ledger ordering without a direct index path.

## Change

1. Added `ix_txn_port_settlement_date_id` on `transactions(portfolio_id, settlement_date, id)`.
2. Added Alembic migration
   `b0c1d2e3f4a6_perf_add_transaction_settlement_date_index.py`.
3. Changed projected settlement cashflow filters to half-open timestamp ranges over raw
   `settlement_date`.
4. Preserved grouping/projection by settlement business date for the API response.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_query_cashflow_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py alembic/versions/b0c1d2e3f4a6_perf_add_transaction_settlement_date_index.py src/services/query_service/app/repositories/cashflow_repository.py tests/unit/services/query_service/repositories/test_query_cashflow_repository.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py alembic/versions/b0c1d2e3f4a6_perf_add_transaction_settlement_date_index.py src/services/query_service/app/repositories/cashflow_repository.py tests/unit/services/query_service/repositories/test_query_cashflow_repository.py`

Results:

1. Focused model and cashflow repository proof: `19 passed`
2. Alembic head proof: `b0c1d2e3f4a6 (head)`
3. Migration contract smoke: passed
4. Touched-surface ruff: passed
5. Touched-surface format check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. Projected settlement
cashflow reads now keep business-date semantics while allowing a portfolio/settlement-date index to
support the range scan.
