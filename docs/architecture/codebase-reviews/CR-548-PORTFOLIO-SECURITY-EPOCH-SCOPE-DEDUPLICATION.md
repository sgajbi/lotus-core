# CR-548: Portfolio Security Epoch Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository evidence detail reads for position history, daily
position snapshots, and valuation jobs.

## Finding

`OperationsRepository` repeated the same portfolio, normalized security, epoch, and as-of evidence
scope across latest position-history date, latest daily-snapshot date, and latest valuation-job
reads. These are support-read paths used to explain replay, valuation, and snapshot coverage state,
so predicate drift between the three lookups would weaken operator evidence and troubleshooting
consistency.

The three reads intentionally differ only in selected model, selected column, and as-of timestamp
columns.

## Change

1. Added `_apply_portfolio_security_epoch_scope(...)` for portfolio/security/epoch evidence
   lookups.
2. Reused the helper from latest position-history date, latest daily-snapshot date, and latest
   valuation-job reads.
3. Preserved normalized security matching, invalid-security short-circuit behavior, as-of timestamp
   guards, valuation job ordering, scalar execution shape, and response types.
4. Tightened query-shape tests to assert normalized security and portfolio predicates on the three
   affected reads.

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
is a maintainability hardening slice that keeps high-value replay, snapshot, and valuation support
evidence reads aligned to one portfolio/security/epoch scope.
