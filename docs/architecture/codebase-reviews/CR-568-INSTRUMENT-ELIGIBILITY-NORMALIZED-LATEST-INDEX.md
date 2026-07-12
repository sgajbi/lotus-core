# CR-568: Instrument Eligibility Normalized Latest Index

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`list_instrument_eligibility_profiles(...)` intentionally trims caller and stored `security_id`
values so padded identifiers do not break DPM eligibility evidence reads. The table only declared a
raw `security_id` effective-window index, so the normalized predicate did not have a matching
PostgreSQL expression index.

The same read also fetched all effective rows for the requested securities and selected the latest
row per security in Python.

## Change

Added model and Alembic index `ix_instr_elig_norm_sec_eff` on:

1. `trim(security_id)`
2. descending `effective_from`
3. `effective_to`
4. descending `observed_at` with nulls last
5. descending `eligibility_version`
6. descending `updated_at`

Added `_ranked_instrument_eligibility_ids(...)` and routed instrument eligibility reads through SQL
`row_number()` partitioned by normalized security id. The query now returns only `rn = 1` rows in
normalized security order.

## Impact

This aligns the DPM instrument eligibility source-data read with its normalized predicate and latest
effective-row ordering, reducing read amplification without changing response shape, API route
shape, or platform contracts.

Repo-local wiki migration guidance was updated. Wiki publication must wait until after merge to
`main`.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q` - 27 passed
2. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py -q` - 18 passed
3. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q` - 99 passed
4. `python -m alembic heads` - `c0fcd4e5f6a7 (head)`
5. `python scripts/migration_contract_check.py --mode alembic-sql` - passed
6. `python scripts/test_manifest.py --suite unit-db --quiet` - 9 passed
7. touched-surface `python -m ruff check` - passed
8. touched-surface `python -m ruff format --check` - passed
9. `git diff --check` - passed
10. `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` - expected `Database-Migrations.md` publication drift while this branch is unmerged
