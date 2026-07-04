# Application Dependency Inversion Standard

Application services must depend on domain/application ports for external capabilities and leave
concrete infrastructure creation to adapters or runtime composition.

## Required Pattern

1. Application services may coordinate use cases, policies, DTO mapping, and domain outcomes.
2. Application services must not introduce new direct dependencies on SQLAlchemy `AsyncSession`,
   broad concrete repository classes, Kafka producer implementations, downstream clients, cache
   clients, object stores, clocks, UUID generators, or helper functions when a port boundary exists.
3. Runtime provider modules and adapter modules may construct concrete repositories, clients,
   publishers, and store implementations.
4. Use fake ports in unit tests when proving application use-case behavior.
5. Add a deterministic architecture guard when an inverted dependency is likely to regress.
6. Keep existing concrete repositories as adapter implementations until their use cases are safely
   migrated behind narrower ports.

## Current Protected Scope

The current guard protects the representative application modules that already have governed port
boundaries:

1. ingestion job idempotency and replay-audit workflows,
2. ingestion event publishing,
3. `PortfolioTaxLotWindow:v1` repository reads,
4. financial reconciliation repository orchestration.

This is not a claim that every query-service application service has been inverted. Services such
as core snapshot, integration, portfolio, position, transaction, cash account, FX rate, and price
still carry direct repository/session dependencies and remain follow-up migration scope.

## Enforcement

`make architecture-guard` runs `scripts/application_dependency_inversion_guard.py` together with
the catalog and specific port-regression guards.

The guard fails if a protected application module reintroduces direct SQLAlchemy sessions, concrete
Kafka producer APIs, broad concrete repository imports, or direct helper calls for capabilities
that now have ports.

## Runtime Boundary

This standard improves design-time modularity and testability inside the existing `lotus-core`
deployables. It does not introduce a runtime microservice split, new database ownership boundary,
new queue, or new deployment topology.
