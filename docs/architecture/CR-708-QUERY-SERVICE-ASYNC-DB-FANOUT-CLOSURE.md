# CR-708: Query Service Async DB Fan-Out Closure

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

After CR-707 fixed the Docker-smoke regression, a residual query-service scan still found
`asyncio.gather(...)` fan-out in services that use one request-scoped SQLAlchemy `AsyncSession`:
analytics timeseries support reads, benchmark market-series evidence reads, simulation projected
positions, and core snapshot projected price/FX resolution. These paths were not the immediate
smoke failure, but they shared the same runtime hazard and could fail under production request
traffic.

## Change

Removed the remaining same-session service-layer DB fan-out and converted the affected reads to
deterministic sequential awaits. The only remaining service-layer async coordination is the
FX-conversion cache's internal lock/task handling, which is not a repository read fan-out pattern.

Updated focused tests from concurrency-start assertions to behavior and ordering checks for:

1. analytics position-currency FX map reads;
2. portfolio and position analytics page support reads;
3. benchmark market-series evidence inputs;
4. simulation baseline/change reads;
5. core snapshot projected security price reads.

## Impact

This closes the query-service request-session boundary across the currently scanned service layer.
It prevents latent `AsyncSession` connection-provisioning failures without changing API contracts,
database schema, wiki source, or platform contracts. Future read parallelism must be introduced
through a governed separate-session read executor rather than ad hoc `asyncio.gather(...)` on
request-scoped repositories.

## Validation

Local validation passed:

1. focused analytics-timeseries, integration, simulation, and core-snapshot service proof
2. touched-surface `python -m ruff check`
3. touched-surface `python -m ruff format --check`
4. `git diff --check`
