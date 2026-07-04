# CR-1310 Application Port Capability Catalog

## Scope

Issue cluster: GitHub issue #651.

This slice defines the governed application port layer and capability catalog for representative
`lotus-core` use cases.

## Objective

Turn the recent port extractions into a discoverable and enforceable architecture pattern so future
use cases do not repeat broad concrete repository, Kafka producer, store helper, or provider
coupling.

## Changes

1. Added `docs/standards/application-port-layer-standard.md`.
2. Added `docs/architecture/application-port-capability-catalog.json`.
3. Added `docs/architecture/application-port-capability-catalog.md`.
4. Added `scripts/application_port_catalog_guard.py` and unit tests.
5. Wired `application-port-catalog-guard` into `make architecture-guard`.
6. Linked the catalog from repo context and the codebase review ledger.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, repository SQL, database schema, Kafka
topic, event payload, source-data product field, reconciliation result, metric name, runtime
composition, or deployment topology changed.

This is design-time modularity and governance only. It does not introduce a new service split.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/scripts/test_application_port_catalog_guard.py -q`
2. `python scripts/application_port_catalog_guard.py`
3. Scoped Ruff lint and format checks for the new guard and tests.
4. `make architecture-guard`

Final command results are recorded before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, architecture catalog docs, codebase review ledger, and repo context.

No wiki update is required because this slice changes internal architecture governance, not
operator-facing commands, route behavior, supported features, or published wiki truth.

No new platform skill change is required in this slice because platform skill guidance was already
updated in `lotus-platform` commit `3cdaadd` to capture issue-driven port-refactor learning.

## Remaining Work

GitHub issue #651 is locally fixed for representative ports-layer and catalog acceptance pending PR
CI/QA and issue closure.

Future issue slices should add new capabilities to the catalog when they introduce governed
application ports for downstream clients, unit-of-work boundaries, cache stores, or additional
repository readers/writers.
