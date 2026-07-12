# CR-518: DPM Model Source Index Hardening

Date: 2026-05-31

## Scope

Query-service source-data reads for DPM model evidence:

1. `DpmModelPortfolioTarget:v1`
2. `CioModelChangeAffectedCohort:v1`

## Finding

`ReferenceDataRepository.resolve_model_portfolio_definition(...)` resolves the approved model
portfolio definition for an as-of date before downstream model-target, affected-cohort, and
readiness workflows consume the model. The query filters by `model_portfolio_id`, approved
lifecycle status, and effective-date window, then orders by latest effective date, approval
timestamp, and update timestamp.

`ReferenceDataRepository.list_model_portfolio_targets(...)` resolves active model targets for a
single model version and as-of date, then orders rows by instrument and latest effective date before
deduplicating to the latest target per instrument.

Both reads are source-data hot paths for discretionary mandate portfolio management. Existing
indexes covered generic effective windows but omitted the governed lifecycle status predicates and
target/definition ordering. The repository predicates also wrapped status columns in
`lower(trim(...))`, preventing direct use of status-aware indexes despite ingestion DTOs constraining
the stored lifecycle values to lowercase contract values.

## Change

1. Added partial index `ix_model_port_def_approved_eff_order` for approved model definitions on
   `(model_portfolio_id, effective_from DESC, effective_to, approved_at DESC, updated_at DESC)`.
2. Added partial index `ix_model_port_tgt_active_eff_order` for active model targets on
   `(model_portfolio_id, model_portfolio_version, instrument_id, effective_from DESC,
   effective_to)`.
3. Added Alembic migration `c0f2a3b4c5d6_perf_add_dpm_model_source_indexes.py` to normalize
   existing model definition/target lifecycle statuses and create the partial indexes.
4. Changed DPM model evidence predicates to compare directly against governed stored lifecycle
   values.
5. Added model metadata proof and query-shape proof that the source-data reads no longer wrap the
   model lifecycle status columns.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python scripts/test_manifest.py --suite unit-db --quiet`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/reference_data_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_reference_data_repository.py alembic/versions/c0f2a3b4c5d6_perf_add_dpm_model_source_indexes.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/reference_data_repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_reference_data_repository.py alembic/versions/c0f2a3b4c5d6_perf_add_dpm_model_source_indexes.py`
7. `git diff --check`

Results:

1. Focused model and reference-data repository proof: `41 passed`
2. Alembic head proof: `c0f2a3b4c5d6 (head)`
3. Migration SQL smoke: passed
4. Unit-db migration apply suite: `9 passed`
5. Touched-surface ruff: passed
6. Touched-surface format check: passed
7. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape or platform contract change was required. This is a storage-contract hardening
change for existing DPM source-data model evidence queries.
