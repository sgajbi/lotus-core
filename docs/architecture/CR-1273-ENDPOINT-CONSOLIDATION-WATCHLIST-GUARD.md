# CR-1273 Endpoint Consolidation Watchlist Guard

- Date: 2026-07-04
- Scope: RFC-0083 endpoint consolidation governance
- GitHub issue: #461

## Objective

Close the defect class where convenience endpoints can remain classified under RFC-0082 while
drifting into consumer-specific APIs that bypass durable source-data products.

## Expected Improvement

Endpoint consolidation is now executable governance instead of prose-only disposition:

1. monitored convenience-route families must appear in a machine-readable watchlist,
2. active watchlist routes must still exist in the route inventory,
3. retired watchlist routes must not be reintroduced,
4. source-data-product routes must bind to the declared product metadata,
5. bounded non-product routes must carry approved rationale, boundary guardrail, and consumer
   guidance.

This reduces API design-time drift and makes future route additions fail fast in local lint.

## Tests Added

Added `tests/unit/scripts/test_endpoint_consolidation_watchlist_guard.py` covering:

1. current watchlist validity,
2. monitored route without disposition,
3. required source-data product identity missing,
4. bounded non-product route with approved rationale,
5. retired route reintroduced,
6. duplicate active watchlist entry,
7. invalid monitor shape.

## Validation Evidence

Local evidence for this slice:

1. `python -m pytest tests/unit/scripts/test_endpoint_consolidation_watchlist_guard.py tests/unit/scripts/test_route_contract_family_guard.py tests/unit/scripts/test_source_data_product_contract_guard.py -q`
   passed with 32 tests.
2. `make endpoint-consolidation-watchlist-guard` passed.
3. `make route-contract-family-guard` passed.
4. `make source-data-product-contract-guard` passed.
5. scoped Ruff lint and format checks for the new guard and test passed.
6. `make lint` passed, including the new endpoint-consolidation watchlist guard.
7. `make quality-wiki-docs-gate` passed.
8. `git diff --check` passed with Windows CRLF normalization warnings only.
9. `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
   reported expected pre-merge publication drift for `API-Surface.md` because this branch changes
   the repo-authored wiki source. Publish after merge.

## Downstream Compatibility Impact

No runtime handler, route path, HTTP status, request DTO, response DTO, OpenAPI output, persistence,
Kafka topic, or database schema changed. This is a local governance and documentation hardening
slice.

## Documentation Updates

Updated RFC-0083 endpoint-consolidation documentation, repository context, README command list, and
repo-local wiki API surface source so API reviewers can find the executable watchlist.
