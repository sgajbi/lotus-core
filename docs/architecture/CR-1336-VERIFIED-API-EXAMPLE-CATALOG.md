# CR-1336 Verified API Example Catalog

## Scope

Issue cluster: GitHub issue #621.

## Objective

Provide a versioned, synthetic, test-validated API example catalog for success, validation error,
authorization denial, not found, idempotency conflict, dependency timeout, degraded source-data,
and pagination/filtering/sorting behavior.

## Changes

1. Added `docs/standards/verified-api-examples.v1.json` with representative examples mapped to
   RFC-0082 route families and source test references.
2. Added `scripts/api_example_catalog_guard.py` and `make api-example-catalog-guard`.
3. Wired the guard into `make architecture-guard`.
4. Added guard tests for required category coverage, route-family links, registered route keys,
   source-test references, correlation IDs, problem fields, idempotency metadata, degraded-source
   metadata, pagination metadata, and synthetic-only posture.
5. Linked the catalog from the API Surface wiki page and repo context.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI schema, database schema, Kafka contract, metric,
deployment topology, package import path, or public API behavior changed.

The catalog is documentation and contract evidence only. It does not introduce new API semantics;
it records representative examples that must stay aligned with implementation-backed tests.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/scripts/test_api_example_catalog_guard.py -q`
2. `python scripts/api_example_catalog_guard.py`
3. `python scripts/wiki_validation_guard.py`
4. `python -m ruff check scripts/api_example_catalog_guard.py tests/unit/scripts/test_api_example_catalog_guard.py --ignore E501,I001`
5. `python -m ruff format --check scripts/api_example_catalog_guard.py tests/unit/scripts/test_api_example_catalog_guard.py`
6. `git diff --check`

## Documentation, Wiki, Context, And Skill Decision

Updated the API example catalog, API Surface wiki source, repo context, and review ledger because
API documentation evidence truth changed.

Wiki source changed and must be published after merge to `main`.

No platform skill source change is required. The durable lesson is enforced through a repo-native
guard and source-test-linked catalog instead of passive prose.

## Remaining Work

GitHub issue #621 is locally fixed for representative verified API example coverage pending PR
CI/QA, post-merge wiki publication, and issue closure. Future route-specific examples should extend
the catalog with source-test references before adding prose to wiki pages.
