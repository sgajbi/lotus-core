# CR-496: Sell State Transaction Index Hardening

Date: 2026-05-28

## Scope

Sell-state disposal history reads used by query-service private-banking transaction support APIs.

## Finding

`SellStateRepository.get_sell_disposals(...)` filters `transactions` by raw `portfolio_id`,
normalized `security_id`, `transaction_type = 'SELL'`, and returns rows ordered by
`transaction_date DESC, id DESC`.

Existing transaction indexes covered either portfolio/type/date or portfolio/normalized-security/date
shapes, but not the combined sell-state predicate. That meant a high-volume security history could
still scan more rows than necessary before returning sell disposals in deterministic reverse
chronology.

## Change

Added SQLAlchemy model index and Alembic migration
`c0d3e4f5a6b7_perf_add_sell_state_transaction_index.py`:

1. `ix_txn_port_norm_sec_type_date_id` on
   `transactions(portfolio_id, trim(security_id), transaction_type, transaction_date DESC, id DESC)`.

Added focused repository query-shape proof that sell-state disposal reads retain the deterministic
reverse chronology expected by the new index.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_sell_state_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_sell_state_repository.py alembic/versions/c0d3e4f5a6b7_perf_add_sell_state_transaction_index.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_sell_state_repository.py alembic/versions/c0d3e4f5a6b7_perf_add_sell_state_transaction_index.py`

Results:

1. Focused model and sell-state repository proof: `11 passed`
2. Alembic head proof: `c0d3e4f5a6b7 (head)`
3. Migration contract smoke: passed
4. Touched-surface ruff: passed
5. Touched-surface format check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. Sell-state disposal
history now has an index aligned to its normalized-security, transaction-type, and deterministic
reverse-chronology query shape.
