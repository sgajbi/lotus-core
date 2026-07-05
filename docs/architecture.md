# lotus-core Architecture

`lotus-core` is the authoritative service for portfolio, booking, account, holding, mandate, and
transaction domain data in the Lotus ecosystem.

## Service Role

1. Own authoritative portfolio and transaction source data.
2. Provide operational read-plane APIs through query-service surfaces.
3. Provide governed control-plane and source-data product contracts for downstream services.
4. Preserve domain ownership boundaries with `lotus-gateway`, `lotus-manage`, `lotus-performance`,
   and other consumers.

## Target Architecture Direction

1. Routers remain thin and call application services or use cases.
2. Routers must not own database sessions, repository construction, Kafka/Redis/cloud/downstream
   clients, file access, domain calculations, or workflow orchestration; see
   `docs/architecture/api-layer-router-boundary-contract.md`.
3. Application modules own use-case orchestration, command/query handling, application errors,
   workflow policies, and calls to ports; see
   `docs/standards/application-layer-contract.md`.
4. Services coordinate validation, read orchestration, conversion, and response assembly through
   focused helper modules when a path has not yet moved fully into an application package.
5. Protected domain, application, port, policy, and pure reducer modules must remain testable
   without FastAPI, real databases, Kafka, Redis, cloud SDKs, or downstream clients; see
   `docs/standards/testability-architecture-standard.md`.
6. New deployable services, workers, schedulers, or runtime boundaries require design-before-runtime
   decision evidence; see `docs/standards/runtime-boundary-decision-standard.md`.
7. Deployable services should use the standard in-process package layout before runtime splits are
   considered; see `docs/standards/in-process-modularity-package-standard.md`.
8. In-process domain, application, ports, adapters, and proof-builder packages are protected by
   import contracts with owned expiring exceptions; see
   `docs/standards/in-process-boundary-contract-standard.md`.
9. Evidence-producing capabilities use typed in-process proof builders before any proof-service
   runtime split is considered; see `docs/standards/proof-builder-pattern-standard.md`.
10. API adapters use bounded mapper modules for DTO-to-command, application-result-to-response, and
   typed error-to-HTTP translation; see `docs/standards/api-mapper-pattern-standard.md`.
11. Boundary anti-corruption across API DTOs, Kafka payloads, persistence records, repository read
   records, and source-data envelopes is explicit and representative-gated; see
   `docs/architecture/mapping-anti-corruption-boundary.md`.
12. Application workflows use runtime provider ports for current time, monotonic elapsed duration,
   TTL decisions, and generated IDs; see `docs/standards/runtime-provider-port-standard.md`.
13. Ingestion business services and adapter-mode policy stay framework-neutral; FastAPI dependency
   providers and HTTP policy translation live in `app/dependencies.py`; see
   `docs/standards/ingestion-service-framework-boundary-standard.md`.
14. Bulk upload handling stays split across pure parsing/validation, commit orchestration, and a
   publisher adapter; see `docs/standards/bulk-upload-component-boundary-standard.md`.
15. Transaction replay stays split across pure replay planning, reader ports, and publisher
   adapters; see `docs/standards/transaction-replay-boundary-standard.md`.
16. Portfolio aggregation scheduler policy stays split across scheduler ports, infrastructure
   adapters, and pure dispatch planning; see
   `docs/standards/aggregation-scheduler-boundary-standard.md`.
17. Position calculation rules and backdated replay decisions stay pure and separate from
   persistence, outbox, metrics, and epoch-fencing orchestration; see
   `docs/standards/position-reducer-boundary-standard.md`.
18. Repositories own persistence access.
19. Shared cross-cutting behavior lives in `portfolio_common` or platform-owned standards where
   appropriate.
20. API contracts remain source-data-product aware, metadata-rich, and implementation-backed.

## Current Refactor Evidence

The current branch has extracted multiple transaction ledger and realized-tax boundaries out of
`TransactionService`. See `docs/architecture/CODEBASE-REVIEW-LEDGER.md` entries CR-832 through
CR-845 for detailed evidence.
