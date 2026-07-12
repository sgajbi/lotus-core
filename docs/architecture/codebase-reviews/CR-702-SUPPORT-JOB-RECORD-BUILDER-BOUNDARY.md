# CR-702: Support Job Record Builder Boundary

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Support-job status normalization, staleness classification, retry detection, terminal-failure
classification, operational-state mapping, and `SupportJobRecord` assembly lived inside the large
`OperationsService` class. That coupled reusable operator DTO construction to the monolithic
operations service while valuation, aggregation, and reprocessing job endpoints all depended on the
same policy.

## Change

Added `support_job_record_builder.py` as the focused boundary for support-job status policy and
`SupportJobRecord` construction. `OperationsService` keeps compatibility wrapper methods for
existing internal callers and tests, but delegates the reusable policy to the new module.

Added focused builder coverage for status/security normalization and processing-staleness
classification.

## Impact

This reduces operations-service size and keeps support-job DTO policy reusable across valuation,
aggregation, and reprocessing drilldowns while preserving response shape, status semantics,
staleness thresholds, security-id normalization, database schema, wiki source, and platform
contracts.

## Validation

Local validation passed:

1. focused operations-service and support-job-builder proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
