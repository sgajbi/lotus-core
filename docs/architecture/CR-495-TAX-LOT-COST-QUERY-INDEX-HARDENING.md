# CR-495: Tax Lot Cost Query Index Hardening

Date: 2026-05-28

## Scope

Tax-lot, accrued-income offset, transaction-cost, and cost-basis transaction-history query paths
used by query-service buy-state APIs and the cost calculator service.

## Finding

Tax-lot APIs page and filter `position_lot_state` by portfolio, acquisition date, optional
normalized security id, and stable lot identifiers. The existing normalized index covered only
`trim(portfolio_id)` and `trim(security_id)`, so portfolio-wide tax-lot pages and ordered
security-specific lot reads did not have a directly aligned composite index.

Accrued-income offset reads use raw `portfolio_id`, normalized `security_id`, and stable `id`
ordering, but the table only had separate single-column indexes. Transaction-cost persistence and
ledger enrichment repeatedly delete and join by `transaction_costs.transaction_id`, which also
needed an explicit foreign-key lookup index for scale.

Cost-basis recalculation fetched same-security transaction history without an explicit SQL order.
The engine sorts after parsing, but repository-level deterministic ordering makes the database read
contract clearer and lines it up with the existing normalized transaction chronology index.

## Change

Added SQLAlchemy model indexes and Alembic migration
`c0d2e3f4a5b6_perf_add_tax_lot_cost_query_indexes.py`:

1. `ix_position_lot_port_norm_sec_acq_id` on
   `position_lot_state(portfolio_id, trim(security_id), acquisition_date, id)`,
2. `ix_position_lot_port_acq_lot_id` on
   `position_lot_state(portfolio_id, acquisition_date, lot_id)`,
3. `ix_accrued_offset_port_norm_sec_id` on
   `accrued_income_offset_state(portfolio_id, trim(security_id), id)`,
4. `ix_transaction_costs_transaction_id` on `transaction_costs(transaction_id)`.

Updated `CostCalculatorRepository.get_transaction_history(...)` to order by
`transaction_date ASC, transaction_id ASC` before handing rows to the cost-basis engine.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py tests/unit/services/query_service/repositories/test_buy_state_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/services/calculators/cost_calculator_service/app/repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py alembic/versions/c0d2e3f4a5b6_perf_add_tax_lot_cost_query_indexes.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/services/calculators/cost_calculator_service/app/repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py alembic/versions/c0d2e3f4a5b6_perf_add_tax_lot_cost_query_indexes.py`

Results:

1. Focused model, cost repository, and buy-state repository proof: `19 passed`
2. Alembic head proof: `c0d2e3f4a5b6 (head)`
3. Migration contract smoke: passed
4. Touched-surface ruff: passed
5. Touched-surface format check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. Tax-lot, accrued-offset,
and transaction-cost lookup paths now have explicit composite indexes aligned to their API and
calculation query shapes, and cost-basis history reads are deterministic at the repository boundary.
