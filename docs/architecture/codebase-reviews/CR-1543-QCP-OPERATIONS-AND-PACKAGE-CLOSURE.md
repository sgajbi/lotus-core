# CR-1543: QCP Operations And Package Closure

## Objective

Make Query Control Plane the complete owner of operational support behavior and prove that its
released wheel/image starts without Query Service implementation source or repository bind mounts.

## Architecture improvement

The operations route now resolves a QCP-owned application service. Public contracts live under
`app/contracts`, operational policies and use cases under `app/application/operations`, immutable
support evidence under `app/domain`, the repository contract under `app/ports`, and SQLAlchemy
mapping/query execution under `app/infrastructure/operations`. Dependency composition constructs
the concrete adapter; application code has no SQLAlchemy session, persistence-model, or concrete
repository dependency.

Control-stage, reconciliation-run, and lineage projections are mapped into typed evidence before
crossing the adapter boundary. SQL-only reset-watermark query scope remains in infrastructure rather
than the domain model. Repository transaction enforcement now scans modern infrastructure adapter
paths as well as legacy repository folders.

## Runtime improvement

QCP production modules contain no `src.services.query_service` imports. Compose no longer mounts
Query Service source into the QCP container. The deterministic package contract blocks both forms
of regression. A clean Docker build installs only the QCP and `portfolio-common` wheels, imports
`app.main`, and contains no repository-root `src` package.

## Compatibility

External routes, request/response contracts, OpenAPI paths, error behavior, support calculations,
query ordering, pagination, recovery behavior, and database schema remain unchanged. Readiness
continues to fail closed when PostgreSQL is unavailable.

## Validation

- 209 focused operations, adapter, router-dependency, and guard tests passed.
- 1,112 Query Control Plane unit/integration tests passed.
- 561 Query Service unit tests passed after facade removal.
- Strict MyPy passed for all 27 moved operations modules; scoped Ruff and full architecture guards
  passed.
- The clean image imported `app.main`, exposed 75 OpenAPI paths, returned HTTP 200 for liveness,
  `/version`, and OpenAPI, and exposed matching commit, branch, build, repository, version, digest,
  and pipeline metadata. Isolated readiness returned HTTP 503 because no database was supplied.

## Remaining work

#469 owns decomposition of the broad operations application/repository by supportability family.
#717 owns remaining dynamic analytics adapter rows. #715 and #720 remain open until GitHub CI,
release evidence, merge, and exact-mainline validation complete.
