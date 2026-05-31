# CR-709: Query Service Async Gather Guard

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

CR-707 and CR-708 removed unsafe `asyncio.gather(...)` fan-out from request-scoped query-service
repositories, but the boundary was only documented. Without an automated guard, a future latency
slice could reintroduce the same production-only SQLAlchemy `AsyncSession` failure class.

## Change

Added a focused AST-based unit guard that scans `src/services/query_service/app/services/*.py` and
fails when a service-layer file calls `asyncio.gather(...)`. This keeps the rule simple and
reviewable: query services may reduce read volume and improve query shape, but same-request DB
parallelism needs a governed separate-session executor before it can appear in service code.

## Impact

This turns the request-session async DB boundary into executable regression coverage. It protects
API read paths, calculation support reads, simulation reads, source-data product reads, and core
snapshot assembly from silently reintroducing same-session concurrent DB access. No API route
shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. focused async DB session boundary guard
2. touched-surface `python -m ruff check`
3. touched-surface `python -m ruff format --check`
4. `git diff --check`
