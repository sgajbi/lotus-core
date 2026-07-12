# CR-1430: Transaction Processing Compatibility Host

Date: 2026-07-10  
Issue: #468  
Status: In progress

## Objective

Create the real target repository root and prove that one runtime can host the existing cost,
cashflow, and position consumers without spreading legacy implementation coupling.

## Change

- Added `src/services/portfolio_transaction_processing_service/`.
- Added one runtime manager using the shared worker lifecycle, one dispatcher, one health app, and
  port `8085`.
- Added an infrastructure compatibility registry for all six current normal/replay consumers while
  preserving topics, group ids, service prefixes, and the shared DLQ.
- Added tests for exact consumer wiring, six-consumer runtime delegation, and confinement of all
  legacy calculator imports to the infrastructure compatibility adapter.

No empty application/domain scaffolding was added. Those layers will appear only with the real
event mapper, `ProcessTransactionUseCase`, domain models/policies, ports, and adapters.

## Compatibility

No Dockerfile, image, Compose service, deployment manifest, Kafka topic, group id, payload,
idempotency key, retry/DLQ behavior, database transaction, outbox event, health port of an existing
service, route, or OpenAPI contract changed. The compatibility host is importable and tested but is
not yet the authoritative deployed runtime.

## Evidence

- Target service tests -> 3 passed.
- Target `app.main` import proof -> `Portfolio Transaction Processing - Health`.
- Full `make architecture-guard` -> passed.
- Target scoped Ruff lint/format -> passed.
- `git diff --check` -> passed.

## Remaining Work

Next migrate a typed event DTO mapper into a real booked-transaction domain model and
`ProcessTransactionUseCase`, then add repository/outbox/idempotency ports and concrete adapters.
Only after behavior, replay, rollback, load, image, and canonical QA parity may deployment switch
to this host and remove the legacy cost/cashflow/position roots.

No wiki or central skill change is required; the architecture wiki and repository context already
describe the planned target and current-versus-target boundary.
