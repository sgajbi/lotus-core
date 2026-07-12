# CR-513: Reprocessing Job Security Lookup Index Hardening

Date: 2026-05-29

## Scope

Operations support reads for RESET_WATERMARKS reprocessing jobs.

## Finding

Reprocessing job support endpoints filter RESET_WATERMARKS jobs by normalized
`payload.security_id`, status, and stable created/id ordering. Existing indexes support pending
claim priority and broad `(job_type, status, created_at, id)` scans, but no index matches the
operator drilldown that asks for reprocessing jobs affecting one security.

Because source payload identifiers can carry padding, the repository correctly filters through
`trim(payload->>'security_id')`; without a matching expression index, security-scoped replay
support can degrade to broader RESET_WATERMARKS scans.

## Change

1. Added `ix_reproc_resetwm_sec_status_created_id` on
   `(trim(payload->>'security_id'), status, created_at, id)` for RESET_WATERMARKS jobs.
2. Added Alembic migration `c0e8f9a0b1c2_perf_add_reprocessing_security_support_index.py`.
3. Added model metadata and repository query-shape proof for normalized security filtering.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0e8f9a0b1c2_perf_add_reprocessing_security_support_index.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_operations_repository.py alembic/versions/c0e8f9a0b1c2_perf_add_reprocessing_security_support_index.py`
7. `git diff --check`
8. `python scripts/test_manifest.py --suite unit-db --quiet`

Results:

1. Passed: 76 tests.
2. Passed: 218 tests.
3. Passed: single head `c0e8f9a0b1c2`.
4. Passed.
5. Passed.
6. Passed.
7. Passed.
8. Passed: 9 tests.

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. This is an index
hardening change for existing replay/recovery support endpoints.
