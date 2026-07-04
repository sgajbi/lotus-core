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
3. Services coordinate validation, read orchestration, conversion, and response assembly through
   focused helper modules.
4. Repositories own persistence access.
5. Shared cross-cutting behavior lives in `portfolio_common` or platform-owned standards where
   appropriate.
6. API contracts remain source-data-product aware, metadata-rich, and implementation-backed.

## Current Refactor Evidence

The current branch has extracted multiple transaction ledger and realized-tax boundaries out of
`TransactionService`. See `docs/architecture/CODEBASE-REVIEW-LEDGER.md` entries CR-832 through
CR-845 for detailed evidence.
