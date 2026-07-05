# CR-1386 Pipeline Stage Consumer Handler Boundary

- Date: 2026-07-06
- Status: Hardened locally
- GitHub issue: #543
- Control taxonomy: architecture, event processing, idempotency, testability

## Objective

Keep pipeline-orchestrator Kafka consumers as delivery adapters and move dependency assembly,
idempotency claim, transaction-boundary setup, repository construction, and service construction
behind a shared handler/unit-of-work boundary.

## Finding

Pipeline stage consumers directly opened `get_async_db_session()`, created
`IdempotencyRepository`, `PipelineStageRepository`, `OutboxRepository`, and
`PipelineOrchestratorService`, then repeated the same claim-and-register flow in each consumer.
That made message delivery own application composition and repeated transactional workflow code
across processed-transaction, cashflow, portfolio-aggregation, and reconciliation-completion
stages.

## Change

Added `PipelineStageMessageHandler` under `pipeline_orchestrator_service.app.application`. The
handler owns the shared idempotency claim and stage-registration flow through a
`PipelineStageUnitOfWork` protocol.

Added `SqlAlchemyPipelineStageUnitOfWork` under `app.adapters` to preserve the existing SQLAlchemy
session, transaction, repository, outbox, and `PipelineOrchestratorService` composition behind that
protocol.

The four pipeline stage consumers now decode/validate events, resolve correlation context, delegate
to the handler, and keep their existing invalid-payload, DB retry, and defensive DLQ behavior.

## Compatibility

No Kafka topic, event payload, event key, event header, idempotency key, database schema, outbox
payload, route, OpenAPI contract, metric, or runtime topology changed. DBAPI/Integrity errors
still propagate to the existing consumer retry decorator. Invalid payloads still route to DLQ from
the consumer layer.

## Same-Pattern Scan

Scanned all pipeline stage consumers for direct `get_async_db_session`, `IdempotencyRepository`,
`PipelineStageRepository`, `OutboxRepository`, and `PipelineOrchestratorService` usage. The
processed-transaction, cashflow, portfolio-aggregation, and reconciliation-completion consumers no
longer assemble those dependencies. A static regression test now pins that boundary.

## Validation

Focused validation before commit:

1. `python -m pytest tests/unit/services/pipeline_orchestrator_service/application/test_pipeline_stage_message_handler.py tests/unit/services/pipeline_orchestrator_service/consumers/test_processed_transaction_stage_consumer.py tests/unit/services/pipeline_orchestrator_service/consumers/test_financial_reconciliation_completion_consumer.py -q`
2. Scoped Ruff check/format on touched source and tests.
3. Pipeline-orchestrator runtime import proof with service-local `PYTHONPATH`.
4. `make architecture-guard`
5. `make quality-wiki-docs-gate`

## Guidance Decision

Repository context was updated because this is a reusable pipeline-orchestrator boundary rule. No
platform skill update was needed; the existing backend and issue-loop skills already require
same-pattern scans and guidance review. No wiki update was required because no operator-facing
behavior or public repository navigation changed.
