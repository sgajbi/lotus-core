# CR-514: Realized Tax Evidence Index Hardening

Date: 2026-05-29

## Scope

Portfolio realized tax evidence reads used by the bounded `PortfolioRealizedTaxSummary:v1`
source-data product.

## Finding

`TransactionRepository.list_realized_tax_evidence_transactions` intentionally restricts the
portfolio ledger to transactions carrying explicit booked withholding-tax or other-interest
deduction evidence, then orders by currency, transaction date, and transaction id for deterministic
aggregation.

Existing transaction indexes support generic portfolio/date, normalized security, type, settlement,
and FX drilldowns, but no index narrows the realized-tax evidence subset. On large private-banking
books this can force broad portfolio ledger scans for a comparatively sparse evidence class.

## Change

1. Added `ix_txn_realized_tax_evidence_port_currency_date_txn` on
   `(portfolio_id, currency, transaction_date, transaction_id)`.
2. Scoped the index with a partial predicate:
   `withholding_tax_amount IS NOT NULL OR other_interest_deductions_amount IS NOT NULL`.
3. Added Alembic migration `c0e9f0a1b2c3_perf_add_realized_tax_evidence_index.py`.
4. Added model metadata proof that the partial index remains aligned to the source-data product
   query shape.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_transaction_repository.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_transaction_repository.py alembic/versions/c0e9f0a1b2c3_perf_add_realized_tax_evidence_index.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_transaction_repository.py alembic/versions/c0e9f0a1b2c3_perf_add_realized_tax_evidence_index.py`
7. `git diff --check`

Results:

1. Passed: 35 tests.
2. Passed: 219 tests.
3. Passed: single head `c0e9f0a1b2c3`.
4. Passed.
5. Passed.
6. Passed.
7. Passed.

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. This is index hardening
for existing realized-tax source evidence retrieval.
