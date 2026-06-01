# CR-542: Support Health Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository job-health summary reads.

## Finding

The valuation, aggregation, and analytics-export health summary queries manually applied the same
portfolio and as-of predicates already centralized for their support count/list query families.
For valuation jobs, that also meant repeating the actionable-job visibility policy indirectly
instead of going through the same governed scope helper as the paged support reads.

That made the support overview path vulnerable to drifting from the underlying job list and count
queries that operators use to investigate the same backlog.

## Change

1. Reused `_apply_valuation_job_scope(...)` in `get_valuation_job_health_summary(...)`.
2. Reused `_apply_aggregation_job_scope(...)` in `get_aggregation_job_health_summary(...)`.
3. Reused `_apply_analytics_export_job_scope(...)` in
   `get_analytics_export_job_health_summary(...)`.
4. Preserved existing selected columns, aggregate definitions, oldest-open ordering, valuation
   actionable-job semantics, as-of behavior, and response shape.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
5. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
6. `git diff --check`

Results:

1. Focused operations repository proof passed.
2. Alembic reported a single current head.
3. Migration SQL contract smoke passed.
4. Touched-surface ruff passed.
5. Touched-surface format check passed.
6. Whitespace check passed.

## Closure

Status: Hardened.

No database migration, API route shape, wiki source, or platform contract change was required. This
is a maintainability hardening slice that keeps support health summaries aligned with the governed
job support count/list scopes.
