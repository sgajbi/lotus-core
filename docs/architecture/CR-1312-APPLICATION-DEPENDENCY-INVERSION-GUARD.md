# CR-1312 Application Dependency Inversion Guard

## Scope

Issue cluster: GitHub issue #645.

This slice consolidates the representative port extractions into a single dependency-inversion
regression guard for application services.

## Objective

Prevent the fixed issue pattern from returning: application services directly importing SQLAlchemy
sessions, broad concrete repositories, Kafka producer implementations, or direct helper functions
after a governed port exists for that capability.

## Changes

1. Added `scripts/application_dependency_inversion_guard.py`.
2. Added focused unit tests for allowed port-enabled modules and rejected concrete dependencies.
3. Wired `application-dependency-inversion-guard` into `make architecture-guard`.
4. Added `docs/standards/application-dependency-inversion-standard.md`.
5. Updated the application port standard, application port catalog, repo context, and review
   ledger.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, repository SQL, database schema, Kafka
topic, Kafka key, Kafka header, event payload field, reconciliation result, metric name, runtime
composition behavior, or deployment topology changed.

This is design-time modularity and enforcement only. It does not introduce a new runtime service
split.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/scripts/test_application_dependency_inversion_guard.py tests/unit/scripts/test_application_port_catalog_guard.py tests/unit/scripts/test_repository_port_guard.py tests/unit/scripts/test_event_publisher_port_guard.py tests/unit/scripts/test_ingestion_store_port_guard.py -q`
2. `python scripts/application_dependency_inversion_guard.py`
3. Scoped Ruff lint and format checks for the new guard and tests.
4. `make architecture-guard`

All listed commands passed locally before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, architecture catalog docs, codebase review ledger, and repo context.

No wiki update is required because this slice changes internal architecture governance, not
operator-facing commands, route behavior, supported features, or published wiki truth.

No new platform skill source change is required in this slice because platform guidance already
directs repeated issue patterns into narrow ports, concrete adapters, fake-port tests, deterministic
guards, and repo context updates.

## Remaining Work

GitHub issue #645 is locally fixed for representative read/write/publisher dependency-inversion
acceptance pending PR CI/QA and issue closure.

The broader migration of remaining query-service application services away from direct
`AsyncSession` and concrete repository construction remains open follow-up issue scope.
