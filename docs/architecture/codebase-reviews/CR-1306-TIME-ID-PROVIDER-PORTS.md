# CR-1306 Time And ID Provider Ports

## Scope

Issue cluster: GitHub issue #655.

This slice expands deterministic time and ID provider coverage across representative reconciliation
and snapshot workflows.

## Objective

Ensure representative application workflows can produce generated IDs, generated timestamps,
elapsed-duration values, and expiry-sensitive behavior without monkeypatching global functions.

## Changes

1. Added `docs/standards/time-id-provider-policy.md`.
2. Reconciliation service already used injected monotonic timer and finding ID generator providers;
   this slice added injected run-ID suffix provider support to `ReconciliationRepository`.
3. Simulation service already accepted injected clock and ID generator providers for session IDs,
   change IDs, and expiry checks.
4. Added injected clock support to `CoreSnapshotService` for generated source-data metadata.
5. Added deterministic unit tests for reconciliation run IDs and core snapshot generated metadata.
6. Added `tests/unit/scripts/test_time_provider_guard.py` as targeted static coverage for the
   representative provider-controlled paths.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, repository method signature, database
schema, Kafka topic, persisted field name, reconciliation finding, snapshot section, simulation
field, metric name, or generated metadata field changed.

Default runtime providers still use system time and UUIDs. Tests and callers may inject fixed
providers.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\financial_reconciliation_service\test_reconciliation_service.py tests\unit\services\financial_reconciliation_service\test_reconciliation_repository.py tests\unit\services\query_service\services\test_core_snapshot_service.py tests\unit\services\query_service\services\test_simulation_service.py tests\unit\scripts\test_time_provider_guard.py -q`
   - 92 passed.
2. Scoped Ruff lint passed.
3. Scoped Ruff format passed.

Final docs and diff evidence is recorded before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated the codebase review ledger, repo-local engineering context, and provider policy standard.

No wiki update is required because this slice changes internal provider governance and deterministic
testability, not operator commands, route behavior, supported features, or published wiki truth.

No central Lotus skill change is required.

## Remaining Work

GitHub issue #655 is locally fixed for the representative provider-port acceptance criteria pending
PR CI/QA and issue closure. Older direct time/UUID sites remain visible in shared runtime,
operations, ingestion diagnostics, and analytics modules; migrate those in separate focused slices
when they affect business behavior or supportability.
