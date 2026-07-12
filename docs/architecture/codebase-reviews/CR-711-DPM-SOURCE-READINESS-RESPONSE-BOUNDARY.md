# CR-711: DPM Source Readiness Response Boundary

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService.get_dpm_source_readiness(...)` still constructed the final
`DpmSourceReadinessResponse` inline after orchestrating the individual DPM source-family reads.
That kept supportability aggregation, lineage, and source-data runtime metadata assembly coupled to
the large integration-service method even though the DPM readiness policy already had a dedicated
helper module.

## Change

Added `build_dpm_source_readiness_response(...)` to `dpm_source_readiness.py` and routed
`IntegrationService` through it after family evidence collection. Focused helper coverage now
proves response supportability, lineage, and runtime metadata are produced by the DPM readiness
policy boundary.

## Impact

This narrows `IntegrationService` to orchestration and keeps DPM readiness response policy in one
module while preserving source-family evaluation, supportability reason codes, lineage, response
shape, API contracts, database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused DPM source-readiness helper and integration-service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
