# CR-1379 Durable Correlation Diagnostics

Date: 2026-07-06

## Objective

Fix GitHub issue #556 by ensuring durable operational records that can legitimately lack a request
correlation ID still persist an explicit missing-correlation reason and deterministic alternate
lookup key.

## Change

- Added `portfolio_common.durable_correlation` as the shared helper for normalizing durable
  correlation evidence.
- Added `correlation_missing_reason` and `alternate_lookup_key` to:
  - `processed_events`,
  - `outbox_events`,
  - `portfolio_aggregation_jobs`,
  - `portfolio_valuation_jobs`,
  - `reprocessing_jobs`.
- Backfilled existing rows where `correlation_id IS NULL` through Alembic and indexed the alternate
  lookup keys for support diagnostics.
- Updated processed-event, outbox, valuation-job, aggregation-job, and reprocessing-job write paths
  to use the shared helper instead of each path inventing local sentinel handling.
- Preserved the CR-1206 consumer-DLQ and replay-audit behavior as the already-fixed companion path.

## Expected Improvement

Operators no longer have to diagnose durable operational records with only a nullable
`correlation_id`. Records without correlation now carry a source-owned reason and semantic lookup
key, so replay/support tooling can search by stable business identifiers when correlation is absent.

## Tests Added Or Updated

- Updated processed-event, outbox, valuation-job, and aggregation-job unit tests to assert missing
  correlation diagnostics.
- Added reprocessing-job integration coverage for missing-correlation diagnostics.
- Extended the existing reprocessing backfill test to prove a later real correlation clears the
  missing-correlation diagnostic fields.

## Validation Evidence

- `python -m py_compile src/libs/portfolio-common/portfolio_common/durable_correlation.py src/libs/portfolio-common/portfolio_common/idempotency_repository.py src/libs/portfolio-common/portfolio_common/outbox_repository.py src/libs/portfolio-common/portfolio_common/valuation_job_repository.py src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py src/services/timeseries_generator_service/app/consumers/position_timeseries_consumer.py alembic/versions/c100b2c3d4e5_feat_add_durable_correlation_diagnostics.py`
  - Result: passed.
- `python -m pytest tests/unit/libs/portfolio-common/test_idempotency_repository.py tests/unit/libs/portfolio-common/test_outbox_repository.py tests/unit/libs/portfolio-common/test_valuation_job_repository.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/consumers/test_position_timeseries_consumer.py::test_stage_aggregation_job_records_missing_correlation_diagnostics tests/unit/services/timeseries_generator_service/timeseries-generator-service/consumers/test_position_timeseries_consumer.py::test_stage_aggregation_jobs_deduplicates_dates_before_bulk_insert -q`
  - Result: passed.
- `python -m alembic heads`
  - Result: passed; single head `c100b2c3d4e5`.
- `make migration-smoke`
  - Result: passed.
- `python -m pytest tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py::test_create_job_records_missing_correlation_diagnostics tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py::test_create_job_backfills_missing_correlation_for_same_impacted_date -q`
  - Result: failed against an already-running stale local Docker schema that predated this migration.
- `$env:LOTUS_TESTS_DOCKER_BUILD='true'; python -m pytest tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py::test_create_job_records_missing_correlation_diagnostics tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py::test_create_job_backfills_missing_correlation_for_same_impacted_date -q`
  - Result: passed, `2 passed in 445.04s`.
- `python -m ruff check src/libs/portfolio-common/portfolio_common/durable_correlation.py src/libs/portfolio-common/portfolio_common/database_models.py src/libs/portfolio-common/portfolio_common/idempotency_repository.py src/libs/portfolio-common/portfolio_common/outbox_repository.py src/libs/portfolio-common/portfolio_common/valuation_job_repository.py src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py src/services/timeseries_generator_service/app/consumers/position_timeseries_consumer.py tests/unit/libs/portfolio-common/test_idempotency_repository.py tests/unit/libs/portfolio-common/test_outbox_repository.py tests/unit/libs/portfolio-common/test_valuation_job_repository.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/consumers/test_position_timeseries_consumer.py tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py alembic/versions/c100b2c3d4e5_feat_add_durable_correlation_diagnostics.py`
  - Result: passed.
- `python -m ruff format --check src/libs/portfolio-common/portfolio_common/durable_correlation.py src/libs/portfolio-common/portfolio_common/database_models.py src/libs/portfolio-common/portfolio_common/idempotency_repository.py src/libs/portfolio-common/portfolio_common/outbox_repository.py src/libs/portfolio-common/portfolio_common/valuation_job_repository.py src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py src/services/timeseries_generator_service/app/consumers/position_timeseries_consumer.py tests/unit/libs/portfolio-common/test_idempotency_repository.py tests/unit/libs/portfolio-common/test_outbox_repository.py tests/unit/libs/portfolio-common/test_valuation_job_repository.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/consumers/test_position_timeseries_consumer.py tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py alembic/versions/c100b2c3d4e5_feat_add_durable_correlation_diagnostics.py`
  - Result: passed.
- `make quality-wiki-docs-gate`
  - Result: passed.
- `make architecture-guard`
  - Result: passed.
- `git diff --check`
  - Result: passed.

## Compatibility

This is an additive internal persistence change. Public API paths, response DTOs, Kafka topics,
event payloads, replay request contracts, and runtime topology are unchanged. Existing rows are
backfilled when migrations run; existing nullable `correlation_id` semantics are preserved.

## Same-Pattern Scan

The prior CR-1206 fix covered consumer DLQ events and replay-audit rows. This slice applies the same
durable-diagnostic pattern to the remaining operational records called out in the issue follow-up:
processed events, outbox events, valuation jobs, aggregation jobs, and reprocessing jobs. Other
request/DTO/event correlation fields are not durable operational lookup records and should not be
expanded with persistence diagnostics unless they become operator-searchable records.

## Documentation And Wiki Decision

Repository context and the codebase review ledger are updated. No wiki source change is required
because no operator command, public API, or supported-feature description changed.

No platform skill change is required: the durable rule is repo-local schema/write-path guidance.
