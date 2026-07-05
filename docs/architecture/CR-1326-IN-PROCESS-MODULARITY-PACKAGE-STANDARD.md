# CR-1326 In-Process Modularity Package Standard

## Scope

Issue cluster: GitHub issue #631.

This slice defines the deployable-service internal package layout that should exist before teams
consider runtime service splits.

## Objective

Make in-process modularity the default expression of conceptual boundaries. Provide a package
standard, migration guidance, dependency-direction rules, and one representative service adoption
so future issues do not use deployable splits to compensate for inconsistent internal package
shape.

## Changes

1. Added `docs/standards/in-process-modularity-package-standard.md` covering recommended
   `domain`, `application`, `ports`, `adapters`, `routers`/delivery, `repositories`/persistence,
   runtime composition, and optional `proof_builders` packages.
2. Clarified where API DTOs/contracts, application commands/results, domain objects, and
   persistence models belong.
3. Added migration guidance for existing `services`, `repositories`, `core`, `transformers`,
   `DTOs`, and `dtos` folders without broad churn.
4. Added dependency-direction examples: delivery/runtime -> application -> domain/ports, and
   adapters/repositories -> ports.
5. Added `docs/architecture/in-process-modularity-adoption-catalog.json` with `ingestion_service`
   as the representative adoption and explicit legacy-folder migration scope.
6. Added `scripts/in_process_modularity_guard.py` and guard tests for representative package paths,
   runtime composition files, evidence links, and legacy-folder classification.
7. Wired `in-process-modularity-guard` into `make architecture-guard`.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, Kafka topic, event payload, database
schema, repository SQL, metric name, runtime wiring, deployment topology, Dockerfile, package
import path, or public behavior changed.

This is design modularity only. It does not create a new deployable service, database, queue, or
operational ownership boundary.

## Representative Adoption

`ingestion_service` is the proving example because it now has domain, application, ports, adapters,
infrastructure, routers, repositories, consumers, and runtime composition files while retaining
legacy `DTOs`, `services`, `transformers`, and `producers` folders as explicit migration scope.

The representative evidence points to the ingestion service framework boundary, bulk upload
component boundary, application command/result standard, application dependency inversion
standard, and recent CR entries that proved fake-port and boundary-guard behavior.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/scripts/test_in_process_modularity_guard.py -q`
2. `python scripts/in_process_modularity_guard.py`
3. `python -m ruff check scripts/in_process_modularity_guard.py tests/unit/scripts/test_in_process_modularity_guard.py --ignore E501,I001`
4. `python -m ruff format --check scripts/in_process_modularity_guard.py tests/unit/scripts/test_in_process_modularity_guard.py`

Aggregate validation before commit:

1. `make architecture-guard`
2. `python scripts/wiki_validation_guard.py`
3. `git diff --check`

All listed commands passed locally before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, architecture overview, codebase review ledger, and repo context.

No wiki update is required because this slice changes internal engineering standards and guard
coverage without changing operator-facing commands, public API behavior, supported features, or
published wiki truth.

No platform skill source change is required in this slice because the repo-local standard and guard
are the actionable implementation for lotus-core package-layout hygiene. The existing backend
delivery skill already requires design modularity before runtime splits.

## Remaining Work

GitHub issue #631 is locally fixed for the package standard, DTO/domain/persistence placement
guidance, migration guidance, dependency-direction examples, representative service adoption, guard
coverage, and architecture-lane wiring pending PR CI/QA and issue closure.

Future slices should add services to the adoption catalog as their workflows move into
domain/application/ports/adapters packages.
