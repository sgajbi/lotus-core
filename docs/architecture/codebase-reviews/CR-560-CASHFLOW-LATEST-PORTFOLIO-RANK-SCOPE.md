# CR-560: Cashflow Latest Portfolio Rank Scope

Date: 2026-05-31

## Scope

Query-service cashflow read-plane latest-cashflow restatement queries.

## Finding

`CashflowRepository._latest_cashflows_subquery()` ranked cashflows by `transaction_id` across the
entire `cashflows` table before the caller applied portfolio, date-window, classification, and
portfolio-flow filters outside the subquery. Every portfolio cashflow projection, evidence
timestamp, cash-movement summary, and external-flow read therefore paid for a global latest-row
window even though each API request is portfolio-scoped.

Pushing date, classification, or flow-type filters into the ranked source would risk changing
restatement semantics: the latest row for a transaction must be selected before deciding whether
that latest row still belongs in a requested date or movement bucket. The portfolio predicate is
safe to push because transaction cashflows are portfolio-owned.

## Change

1. Added an optional portfolio scope to `_latest_cashflows_subquery(...)`.
2. Routed the portfolio cashflow series, latest cashflow evidence timestamp, cash-movement summary,
   and external-flow reads through the portfolio-scoped latest-cashflow subquery.
3. Left date, classification, and flow-type predicates outside the ranked source to preserve latest
   restatement semantics.
4. Added model metadata index `ix_cashflows_port_txn_epoch_id` on `portfolio_id`, `transaction_id`,
   `epoch DESC`, and `id DESC`.
5. Added Alembic revision `c0faa1b2c3d4` to create and drop the index.
6. Strengthened query-shape and model-index tests, and updated repo-local migration guidance.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_query_cashflow_repository.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py -q`
3. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
4. `python -m alembic heads`
5. `python scripts/migration_contract_check.py --mode alembic-sql`
6. `python scripts/test_manifest.py --suite unit-db --quiet`
7. `python -m ruff check src/services/query_service/app/repositories/cashflow_repository.py tests/unit/services/query_service/repositories/test_query_cashflow_repository.py src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py`
8. `python -m ruff format --check src/services/query_service/app/repositories/cashflow_repository.py tests/unit/services/query_service/repositories/test_query_cashflow_repository.py src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py`
9. `git diff --check`

Results:

1. Focused cashflow repository query-shape proof passed.
2. Focused model/index metadata proof passed.
3. Operations repository proof passed to protect adjacent migration-sensitive support reads.
4. Alembic reported a single current head.
5. Migration SQL contract smoke passed.
6. Unit-DB manifest passed.
7. Touched-surface ruff passed.
8. Touched-surface format check passed.
9. Whitespace check passed.

## Closure

Status: Hardened.

No API route shape or platform contract change was required. The repo-local wiki source changed
because database migration guidance now covers portfolio-scoped latest cashflow restatement
indexes. Do not publish the wiki from this unmerged feature branch.
