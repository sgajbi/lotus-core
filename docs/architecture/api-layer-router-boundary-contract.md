# API-Layer Router Boundary Contract

This contract defines what `lotus-core` FastAPI router modules may own.

## Router Responsibilities

Router modules may define:

1. HTTP method, path, tags, status, response model, and OpenAPI examples,
2. request body, query parameter, path parameter, header, and auth context extraction,
3. API-level validation that is specific to HTTP shape,
4. DTO-to-application command/query mapping,
5. application result/error-to-HTTP response mapping,
6. dependency injection for application use cases, auth context, pagination, and request metadata.

Router modules must not own:

1. SQLAlchemy session access or database operations,
2. repository construction or repository method orchestration,
3. Kafka, Redis, object storage, cloud, or downstream HTTP client access,
4. file parsing or local filesystem access,
5. business decisions, domain calculations, or multi-step workflow orchestration,
6. cross-service implementation imports.

## Composition Boundary

Infrastructure wiring belongs in dedicated dependency/composition modules. Routers should depend on
application use cases or ports, not database sessions, repositories, or concrete infrastructure
clients.

## Enforcement

`make architecture-guard` enforces this contract through `scripts/architecture_boundary_guard.py`.
Current legacy router dependencies are listed in
`docs/standards/api-layer-router-boundary-exceptions.json`. The exception registry is transitional:

1. new router files or new violation categories fail the guard,
2. stale exceptions fail once the corresponding violation disappears,
3. every exception must point at an issue and carry a rationale.
