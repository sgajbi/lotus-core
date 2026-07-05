# CR-1327 In-Process Boundary Guard

## Objective

Fix GitHub issue #632 by enforcing package-level dependency boundaries for in-process domain,
application, ports, adapters, and proof-builder packages before additional runtime service splits
are considered.

## Expected Improvement

The slice converts the package layout standard from guidance into a blocking architecture gate.
Future changes cannot silently add FastAPI, SQLAlchemy, Kafka, concrete adapter, repository, API
DTO, legacy service, or persistence-model coupling to protected in-process packages without an
owned, expiring exception and follow-up issue.

## Changes

1. Added `docs/standards/in-process-boundary-contract-standard.md`.
2. Added `docs/standards/in-process-boundary-exceptions.json` with bounded transitional exceptions.
3. Added `scripts/in_process_boundary_guard.py`.
4. Added focused guard tests.
5. Wired `in-process-boundary-guard` into `make architecture-guard`.

## Compatibility Impact

No route path, request DTO, response DTO, OpenAPI metadata, Kafka topic, event payload, database
schema, repository SQL, metric name, runtime wiring, deployment topology, or public behavior
changed. Existing coupling remains only where explicitly registered as migration debt.

## No Runtime Split Decision

This is a design-modularity and enforcement slice inside current deployables. No new service,
worker, scheduler, topic, database, Dockerfile, or deployment boundary is introduced.

## Validation Evidence

Focused validation was run before commit:

1. `python -m pytest tests/unit/scripts/test_in_process_boundary_guard.py -q`
2. `python scripts/in_process_boundary_guard.py`
3. `python -m ruff check scripts/in_process_boundary_guard.py tests/unit/scripts/test_in_process_boundary_guard.py --ignore E501,I001`
4. `python -m ruff format --check scripts/in_process_boundary_guard.py tests/unit/scripts/test_in_process_boundary_guard.py`
5. `make architecture-guard`
6. `python scripts/wiki_validation_guard.py`
7. `git diff --check`

## Documentation And Context

Updated architecture navigation, repository context, and the codebase review ledger. No wiki source
change was required because this adds developer architecture governance, not operator-facing
runtime or runbook behavior.
