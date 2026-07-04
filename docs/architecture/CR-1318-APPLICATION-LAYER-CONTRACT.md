# CR-1318 Application Layer Contract

## Scope

Issue cluster: GitHub issue #641.

This slice defines and enforces the repo-local application-layer contract for current
`app/application` packages.

## Objective

Make the application layer a first-class, testable boundary rather than an informal naming
convention. Preserve current runtime topology and public contracts while preventing migrated
application modules from importing framework or infrastructure concerns.

## Changes

1. Added `docs/standards/application-layer-contract.md`.
2. Linked the application-layer contract from `docs/architecture.md`.
3. Added `scripts/application_layer_contract_guard.py`.
4. Added unit tests for allowed pure application modules and rejected framework/infrastructure
   imports.
5. Wired `application-layer-contract-guard` into `make architecture-guard`.
6. Recorded the current representative workflows that already satisfy the contract:
   ingestion upload command/result, ingestion workflow policies, query lookup results, core
   snapshot identity command, and financial reconciliation use cases.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, repository SQL, database schema, Kafka
topic, metric name, application behavior, or runtime topology changed.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/scripts/test_application_layer_contract_guard.py -q`
2. `python scripts/application_layer_contract_guard.py`

Aggregate validation before commit:

1. `make architecture-guard`
2. `python scripts/wiki_validation_guard.py`
3. `git diff --check`

All listed commands passed locally before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, architecture overview, codebase review ledger, and repo context.

No wiki update is required because this slice changes internal architecture governance and does not
change operator-facing commands, public API behavior, supported features, or published wiki truth.

No platform skill source change is required in this slice because the existing backend delivery
guidance already directs application-layer boundary work toward standards, guards, fake-port tests,
and context updates.

## Remaining Work

GitHub issue #641 is locally fixed for the application-layer standard, representative workflows,
and guard acceptance pending PR CI/QA and issue closure.

Legacy service modules outside `app/application` still need incremental migration as their issue
slices are addressed.
