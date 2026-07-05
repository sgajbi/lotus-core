# API Mapper Pattern Standard

API mappers translate HTTP-facing DTOs, query/path/header context, and application outcomes at the
delivery edge. They make API adapter behavior explicit without moving business decisions into
routers.

## Responsibilities

API mappers may:

1. build application commands or queries from API DTOs, path parameters, query parameters, headers,
   and auth context,
2. map application results into response DTOs,
3. map typed application errors or result variants into HTTP status codes and detail bodies,
4. keep OpenAPI examples and API tests aligned with the implemented response contract.

API mappers must not:

1. query repositories or database sessions,
2. publish Kafka/EventHub records,
3. call Redis, cloud SDKs, object storage, filesystems, or downstream HTTP clients,
4. make domain decisions that belong in application services or domain policies,
5. import persistence models as response inputs.

## Representative Mapper Modules

The current representative mapper modules are:

1. `src/services/query_service/app/routers/lookup_mappers.py`
2. `src/services/financial_reconciliation_service/app/routers/reconciliation_mappers.py`
3. `src/services/event_replay_service/app/routers/replay_mappers.py`
4. `src/services/query_service/app/routers/http_errors.py`

The upload router remains a representative compact mapper for file-upload API DTO to application
command/result conversion. Move upload mapping into a dedicated mapper module if it grows beyond
simple DTO translation.

## Error Mapping

Routers should not repeatedly inline generic `LookupError`, `ValueError`, or command exception
translation when a bounded-context mapper exists. Prefer typed application errors or result
variants, then map them through a small API mapper with focused tests.

## Enforcement

`make architecture-guard` runs `scripts/api_mapper_pattern_guard.py`.

The guard validates representative mapper modules, prevents moved lookup mapping from returning to
the router, blocks direct event-replay command-error HTTP conversion from being reintroduced in the
router, and blocks representative query-service `LookupError`/`ValueError` HTTP conversion from
drifting back into individual routers.

## Runtime Boundary

This is an API adapter design pattern inside existing deployables. It does not create a new
runtime service, endpoint, queue, database, or deployment topology.
