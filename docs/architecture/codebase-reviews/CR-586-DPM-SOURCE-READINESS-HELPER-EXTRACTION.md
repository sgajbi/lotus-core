# CR-586: DPM Source Readiness Helper Extraction

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService.get_dpm_source_readiness(...)` still owned repeated source-family readiness row
construction and the overall readiness-state aggregation directly inside the large integration
service. That mixed source-data product orchestration with reusable DPM readiness vocabulary:

1. family row construction,
2. unavailable-family defaults,
3. missing and stale item preservation,
4. evidence counts, and
5. overall READY/DEGRADED/INCOMPLETE/UNAVAILABLE precedence.

## Change

Added `dpm_source_readiness.py` as a focused helper module with:

1. `dpm_source_family_readiness(...)`,
2. `unavailable_dpm_source_family(...)`, and
3. `dpm_source_readiness_supportability(...)`.

`IntegrationService` now delegates readiness row construction and aggregate supportability
selection to the helper while retaining source-data product calls, resolved mandate/model context,
evaluated instrument selection, lineage envelope, and runtime metadata.

## Impact

This narrows DPM source readiness orchestration toward dependency flow and keeps the private banking
DPM readiness vocabulary in one tested module. API route shape, response fields, OpenAPI contracts,
database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is an internal service-boundary extraction with no
operator-facing workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_dpm_source_readiness.py tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
