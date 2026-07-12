# CR-588: Integration Service Helper Wrapper Cleanup

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

After reference-data helper extraction, `IntegrationService` still kept thin private wrapper methods
around helper-module functions for request fingerprinting, series fingerprinting, latest evidence
timestamp selection, market reference data-quality classification, latest-effective record
selection, and benchmark component-window resolution. These wrappers added protected-access test
coupling and made the large service look like it still owned reusable helper behavior.

## Change

Removed the thin wrappers and routed service call sites directly to the existing helper modules:

1. `request_fingerprint(...)`,
2. `series_request_fingerprint(...)`,
3. `latest_reference_evidence_timestamp(...)`,
4. `market_reference_data_quality_status(...)`,
5. `latest_effective_records(...)`, and
6. `resolve_component_window_rows(...)`.

Tests that previously reached through protected `IntegrationService` helpers now validate the
helper modules directly.

## Impact

This reduces monolithic service surface area and test coupling without changing API route shape,
response fields, repository predicates, database schema, wiki source, or platform contracts.

No wiki update was needed because this is internal service-boundary cleanup with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services/test_reference_data_helpers.py tests/unit/services/query_service/services/test_request_fingerprint.py -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`
