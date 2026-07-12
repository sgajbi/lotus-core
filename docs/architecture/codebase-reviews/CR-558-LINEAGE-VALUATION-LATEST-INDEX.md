# CR-558: Lineage Valuation Latest Index

Date: 2026-05-31

## Scope

Portfolio valuation job indexing for query-service lineage key support reads.

## Finding

CR-557 reduced lineage key listing from four repeated latest valuation-job scalar probes to one
lateral latest-job lookup. The resulting query now has a stable hot-path access pattern:

1. equality on `portfolio_valuation_jobs.portfolio_id`,
2. equality on normalized `portfolio_valuation_jobs.security_id`,
3. equality on `portfolio_valuation_jobs.epoch`,
4. ordering by latest `valuation_date` and `id` for a one-row lookup.

Existing valuation-job indexes primarily serve status-driven queue, stale-scan, and support list
queries. The normalized calculation lookup index includes valuation date and status but does not
match the lineage latest-job ordering. That left the improved lateral query without a dedicated
index for its per-lineage-row latest lookup.

## Change

1. Added model metadata index `ix_val_jobs_lineage_latest` on `portfolio_id`,
   `trim(security_id)`, `epoch`, `valuation_date DESC`, and `id DESC`.
2. Added Alembic revision `c0f8a9b0c1d2` to create and drop the index.
3. Strengthened database model tests to pin the index expression order and the PostgreSQL
   identifier-length guard.
4. Updated the repo-local wiki migration guidance with the lineage latest-job indexing rule.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. `python scripts/test_manifest.py --suite unit-db --quiet`
6. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
7. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
8. `git diff --check`

Results:

1. Focused model/index metadata proof passed.
2. Focused operations repository query-shape proof passed.
3. Alembic reported a single current head.
4. Migration SQL contract smoke passed.
5. Unit-DB manifest passed.
6. Touched-surface ruff passed.
7. Touched-surface format check passed.
8. Whitespace check passed.

## Closure

Status: Hardened.

No API route shape or platform contract change was required. The repo-local wiki source changed
because database migration guidance now records the lineage latest-job indexing rule. Do not publish
the wiki from this unmerged feature branch.
