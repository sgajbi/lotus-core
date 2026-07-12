# CR-517: DPM Mandate Source Index Hardening

Date: 2026-05-31

## Scope

Query-service source-data reads for DPM mandate evidence:

1. `CioModelChangeAffectedCohort:v1`
2. `DpmPortfolioUniverseCandidate:v1`

## Finding

`ReferenceDataRepository.list_model_portfolio_affected_mandates(...)` and
`ReferenceDataRepository.list_dpm_portfolio_universe_candidates(...)` are downstream source-data
hot paths for discretionary mandate portfolio management. They filter `portfolio_mandate_bindings`
by DPM mandate type, active discretionary authority status, optional model portfolio, optional
booking center, and effective-date window before returning deterministic portfolio/mandate rows.

The table only had a generic `(portfolio_id, effective_from, effective_to)` index. That did not
match model-change cohort or DPM universe evidence reads, and the active-status predicate wrapped
the stored value in `lower(trim(...))`, preventing direct use of status-aware indexes.

## Change

1. Added partial index `ix_mandate_binding_dpm_model_book_eff` on
   `(model_portfolio_id, booking_center_code, effective_from, effective_to, portfolio_id,
   mandate_id)` for rows where `mandate_type = 'discretionary'` and
   `discretionary_authority_status = 'active'`.
2. Added Alembic migration `c0f1a2b3c4d5_perf_add_dpm_mandate_source_index.py` to normalize
   existing mandate type/status values and create the partial index.
3. Changed DPM mandate evidence predicates to compare directly against the governed stored active
   status.
4. Added model metadata proof and query-shape proof that the source-data reads no longer wrap the
   active authority status column.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python scripts/test_manifest.py --suite unit-db --quiet`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/reference_data_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_reference_data_repository.py alembic/versions/c0f1a2b3c4d5_perf_add_dpm_mandate_source_index.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/reference_data_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_reference_data_repository.py alembic/versions/c0f1a2b3c4d5_perf_add_dpm_mandate_source_index.py`
7. `git diff --check`

Results:

1. Focused model and reference-data repository proof: `40 passed`
2. Alembic head proof: `c0f1a2b3c4d5 (head)`
3. Migration SQL smoke: passed
4. Unit-db migration apply suite: `9 passed`
5. Touched-surface ruff: passed
6. Touched-surface format check: passed
7. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape or platform contract change was required. This is a storage-contract hardening
change for existing DPM source-data evidence queries.
