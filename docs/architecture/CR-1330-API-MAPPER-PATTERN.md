# CR-1330 API Mapper Pattern

## Objective

Fix GitHub issue #640 by standardizing representative DTO-to-command, application-result-to-DTO,
and application-error-to-HTTP mapping patterns across routers.

## Expected Improvement

The slice moves representative lookup, reconciliation, event-replay, and query-service error
mapping logic into focused API mapper modules and adds a guard so those mappings do not drift back
into broad router functions. It preserves router ownership of HTTP paths, parameters, headers,
dependencies, status codes, and response models while making bounded-context mapping testable
without database, Kafka, or downstream dependencies.

## Changes

1. Added `docs/standards/api-mapper-pattern-standard.md`.
2. Added `lookup_mappers.py`, `reconciliation_mappers.py`, and `replay_mappers.py`.
3. Expanded `query_service` router error mappers for repeated `LookupError` and `ValueError`
   conversion.
4. Updated lookup, reconciliation, event-replay, and representative query-service routers to use
   mapper modules.
5. Added mapper unit tests.
6. Added `scripts/api_mapper_pattern_guard.py` with guard tests.
7. Wired `api-mapper-pattern-guard` into `make architecture-guard`.

## Compatibility Impact

No route path, request DTO, response DTO, OpenAPI metadata, Kafka topic, event payload, database
schema, repository SQL, metric name, runtime wiring, deployment topology, Dockerfile, package
import path, or public behavior changed.

## No Runtime Split Decision

This is an API adapter design pattern inside existing deployables. It does not create a new
service, endpoint, queue, database, worker, or deployment boundary.

## Validation Evidence

Focused validation was run before commit:

1. `python -m pytest tests/unit/services/query_service/routers/test_lookups_router.py tests/unit/services/query_service/routers/test_http_errors.py tests/unit/services/query_service/routers/test_cash_movements_router.py tests/unit/services/financial_reconciliation_service/test_reconciliation_mappers.py tests/unit/services/event_replay_service/test_replay_mappers.py tests/unit/scripts/test_api_mapper_pattern_guard.py -q`
2. `python scripts/api_mapper_pattern_guard.py`
3. Scoped Ruff check over changed mapper/router/guard/test files.
4. Scoped Ruff format check over changed mapper/router/guard/test files.
5. `make architecture-guard`
6. `python scripts/wiki_validation_guard.py`
7. `git diff --check`
