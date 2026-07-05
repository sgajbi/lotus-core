# CR-1353 Analytics Lineage Metadata Collision Guard

## Scope

GitHub issue #705: `lotus-core` query-control-plane analytics reference and portfolio-timeseries
responses must not fail with duplicate `lineage` keyword construction errors when consumed by
`lotus-performance`, `lotus-risk`, and `lotus-idea` proof generation.

## Objective

Preserve source-owned analytics response lineage while preventing runtime source-data metadata from
overriding the response-level `lineage` field. Keep the canonical
`PB_SG_GLOBAL_BAL_001` portfolio proof path covered by lower-level tests.

## Changes

1. Added `_analytics_source_runtime_metadata(...)` in `AnalyticsTimeseriesService`.
2. Routed portfolio timeseries, position timeseries, and portfolio reference response assembly
   through the guarded helper.
3. The guard fails closed with `AnalyticsInputError("UNSUPPORTED_CONFIGURATION", ...)` if a future
   runtime metadata helper returns a reserved `lineage` key instead of `source_lineage`.
4. Added canonical `PB_SG_GLOBAL_BAL_001` service tests for portfolio timeseries and portfolio
   reference response construction.
5. Added a collision regression test proving a future duplicate-lineage metadata shape raises a
   governed application error rather than an unhandled constructor `TypeError`.

## Behavior And Compatibility

Existing successful response fields, route paths, request DTOs, response DTOs, OpenAPI schemas,
database schema, Kafka contracts, metric names, Dockerfiles, deployment topology, and runtime
service boundaries are unchanged.

The only behavior change is defensive: if runtime source metadata incorrectly tries to provide the
response `lineage` field, Core now fails through the analytics application error path instead of
raising an unhandled constructor error.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\query_service\services\test_analytics_timeseries_service.py tests\unit\test_domain_data_product_contracts.py tests\unit\services\query_service\dtos\test_source_data_product_identity.py -q`
   - Result: `100 passed`
2. `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py tests\unit\services\query_service\services\test_analytics_timeseries_service.py`
   - Result: passed
3. `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py tests\unit\services\query_service\services\test_analytics_timeseries_service.py`
   - Result: passed
4. `make quality-wiki-docs-gate`
   - Result: passed

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local context because future Core analytics-source work must preserve the
`lineage` versus `source_lineage` boundary.

No wiki source update is required: operator commands, public API shape, and documented runtime
workflow are unchanged.

No platform skill source change is required in this slice. The repeatable lesson is represented in
the Core context, review ledger, and focused regression tests; the existing backend skill already
requires source-proof metadata fixes to update repo context and tests.

## Remaining Work

Re-run the live local Core query-control-plane endpoints, then downstream `lotus-performance`,
`lotus-risk`, and `lotus-idea` proof generators after the changed Core image/service is refreshed.
This slice locally fixes #705 pending PR CI, live downstream proof, merge, and issue closure.
