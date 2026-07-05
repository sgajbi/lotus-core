# CR-1331 Runtime Provider Ports

## Objective

Fix GitHub issue #655 by introducing shared clock, monotonic timer, and ID generator ports for
deterministic application workflows.

## Expected Improvement

The slice removes direct runtime time/UUID factories from representative reconciliation, core
snapshot, and simulation workflows. Tests now inject fake providers to prove generated timestamps,
TTL expiry, IDs, and elapsed-duration metrics without monkeypatching global functions.

## Changes

1. Added `portfolio_common.runtime_providers`.
2. Kept the reconciliation service-local `runtime_providers.py` as a compatibility re-export.
3. Migrated financial reconciliation finding IDs and elapsed-duration timing to shared providers.
4. Migrated core snapshot generated metadata timestamps to `Clock`.
5. Migrated simulation session IDs, change IDs, creation timestamps, TTLs, and expiry checks to
   `Clock` and `IdGenerator`.
6. Added provider and fake-provider behavior tests.
7. Updated the application port catalog to point at the shared provider contract.
8. Added `docs/standards/runtime-provider-port-standard.md`.
9. Added `scripts/runtime_provider_port_guard.py` and wired it into `make architecture-guard`.

## Compatibility Impact

No route path, request DTO, response DTO, OpenAPI metadata, Kafka topic, event payload, database
schema, repository SQL, metric name, deployment topology, Dockerfile, package import path, or
public API behavior changed. Generated UUID values and current-time values still come from the
same Python runtime sources through system adapters.

## No Runtime Split Decision

This is an in-process application-port pattern. It does not create a new service, endpoint, queue,
database, worker, scheduler, or deployment boundary.

## Remaining Migration Scope

Same-pattern scan found direct time/UUID calls in legacy query-service analytics, operations,
capabilities, integration-policy, advisory-simulation, and support-job builder modules. They remain
follow-up migration scope and are not claimed as fixed by this slice.

## Validation Evidence

Focused validation was run before commit:

1. `python -m pytest tests/unit/libs/portfolio-common/test_runtime_providers.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py tests/unit/services/query_service/services/test_core_snapshot_service.py tests/unit/services/query_service/services/test_simulation_service.py tests/unit/scripts/test_runtime_provider_port_guard.py -q`
2. `python scripts/runtime_provider_port_guard.py`
3. Scoped Ruff check over changed runtime-provider, workflow, guard, and test files.
4. Scoped Ruff format check over changed runtime-provider, workflow, guard, and test files.
5. `make architecture-guard`
6. `python scripts/wiki_validation_guard.py`
7. `git diff --check`
