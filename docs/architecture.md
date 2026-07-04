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
5. Ingestion business services and adapter-mode policy stay framework-neutral; FastAPI dependency
   providers and HTTP policy translation live in `app/dependencies.py`; see
   `docs/standards/ingestion-service-framework-boundary-standard.md`.
6. Bulk upload handling stays split across pure parsing/validation, commit orchestration, and a
   publisher adapter; see `docs/standards/bulk-upload-component-boundary-standard.md`.
7. Transaction replay stays split across pure replay planning, reader ports, and publisher
   adapters; see `docs/standards/transaction-replay-boundary-standard.md`.
8. Portfolio aggregation scheduler policy stays split across scheduler ports, infrastructure
   adapters, and pure dispatch planning; see
   `docs/standards/aggregation-scheduler-boundary-standard.md`.
9. Position calculation rules and backdated replay decisions stay pure and separate from
   persistence, outbox, metrics, and epoch-fencing orchestration; see
   `docs/standards/position-reducer-boundary-standard.md`.
10. Repositories own persistence access.
11. Shared cross-cutting behavior lives in `portfolio_common` or platform-owned standards where
   appropriate.
12. API contracts remain source-data-product aware, metadata-rich, and implementation-backed.

## Current Refactor Evidence

The current branch has extracted multiple transaction ledger and realized-tax boundaries out of
`TransactionService`. See `docs/architecture/CODEBASE-REVIEW-LEDGER.md` entries CR-832 through
CR-845 for detailed evidence.
