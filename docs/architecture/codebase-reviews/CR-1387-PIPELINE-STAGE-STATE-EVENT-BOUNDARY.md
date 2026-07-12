# CR-1387 Pipeline Stage State/Event Boundary

- Date: 2026-07-06
- Status: Hardened locally
- GitHub issue: #544
- Control taxonomy: architecture, state-machine correctness, event/outbox contract quality,
  testability

## Objective

Separate pipeline stage transition decisions from outbox event construction and publication while
preserving existing pipeline readiness and reconciliation-control event behavior.

## Finding

`PipelineOrchestratorService` updated stage state, checked readiness, evaluated reconciliation
control blocking, built event payloads, selected topics, and wrote outbox rows in the same class.
That made the state machine harder to test without outbox dependencies and made topic/event
mapping hard to verify separately from transition logic.

## Change

Added `pipeline_stage_state_machine.py` under `pipeline_orchestrator_service.app.domain` for pure
transaction-stage readiness, control-stage blocking, and stale-epoch emission decisions.

Added `pipeline_event_factory.py` under `app.adapters` for outbox event type, topic, aggregate ID,
and payload construction for:

1. `TransactionProcessingCompleted`,
2. `PortfolioDayReadyForValuation`,
3. `FinancialReconciliationRequested`,
4. `PortfolioDayControlsEvaluated`.

`PipelineOrchestratorService` now coordinates repository updates, calls the state machine, asks the
event factory for messages, and writes those messages to the existing outbox repository.
The mapping anti-corruption guard now enforces the event factory as the pipeline outbox mapping
artifact and rejects direct `pipeline_outbox_event_payload` usage in the orchestrator service.

## Compatibility

No Kafka topic, event type, event payload field, aggregate ID shape, outbox row contract, database
schema, route, OpenAPI contract, metric, or runtime topology changed. Existing service-level tests
continue to prove readiness, non-cashflow FX contract, reconciliation-control blocking,
publish-allowed, and stale-epoch behavior.

## Same-Pattern Scan

The slice focused on pipeline-orchestrator stage decisions and outbox mapping. The new domain tests
exercise transition decisions without any outbox repository. The event-factory tests exercise
topic/event/aggregate/payload mapping without repository state mutation.

## Validation

Focused validation before commit:

1. `python -m pytest tests/unit/services/pipeline_orchestrator_service/domain/test_pipeline_stage_state_machine.py tests/unit/services/pipeline_orchestrator_service/adapters/test_pipeline_event_factory.py tests/unit/services/pipeline_orchestrator_service/services/test_pipeline_orchestrator_service.py -q`
2. Scoped Ruff check/format on touched source and tests.
3. Pipeline-orchestrator runtime import proof with service-local `PYTHONPATH`.
4. `make architecture-guard`
5. `make quality-wiki-docs-gate`

## Boundary Decision

This is an in-process design-modularity improvement inside the existing
`pipeline_orchestrator_service` deployable. No runtime split is justified by this slice: workload,
database ownership, queue ownership, failure isolation, security boundary, and SLO evidence remain
unchanged.

## Guidance Decision

Repository context was updated because future pipeline stage work must preserve the split between
domain state decisions, event mapping, and outbox publication. No platform skill update was needed;
the existing backend and review skills already require same-pattern scans and durable guidance
review. No wiki update was required because no operator-facing behavior or public navigation
changed.
