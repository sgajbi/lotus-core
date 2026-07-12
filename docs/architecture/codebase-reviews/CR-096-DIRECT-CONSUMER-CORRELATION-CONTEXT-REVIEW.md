# CR-096 Direct Consumer Correlation Context Review

## Scope

- direct `process_message(...)` invocation paths for control-plane and valuation consumers
- correlation propagation into idempotency, scheduler, and outbox writes

## Finding

Several consumers still relied on `correlation_id_var.get()` inside `process_message(...)`
without ensuring the correlation context had been initialized locally. That assumption
holds inside `BaseConsumer.run()`, but not when consumers are invoked directly in unit
tests or future in-process replay/control paths.

The pattern risk was systemic:

- valuation readiness
- market-price trigger
- financial reconciliation request/completion
- pipeline stage consumers

Without a local correlation-context guard, direct paths could silently lose Kafka header
correlation or fall back to unrelated generated ids.

## Action Taken

- Added a shared `BaseConsumer._message_correlation_context(...)` helper
- The helper now supports:
  - current context reuse
  - Kafka header correlation resolution
  - deterministic fallback correlation values
  - optional payload-correlation preference where the event already carries the
    canonical correlation id
- Applied the helper to the high-value control-plane and valuation consumers
- Added/extended direct consumer tests proving:
  - header correlation is used where transport correlation is canonical
  - payload correlation is preserved where event-level correlation is canonical

## Result

Direct consumer execution now matches runtime-loop correlation fidelity on the reviewed
high-value consumers. This closes a systemic audit/idempotency gap instead of treating
it as a one-off position-calculator issue.

## Evidence

- `src/libs/portfolio-common/portfolio_common/kafka_consumer.py`
- `src/services/valuation_orchestrator_service/app/consumers/*.py`
- `src/services/financial_reconciliation_service/app/consumers/reconciliation_requested_consumer.py`
- `src/services/pipeline_orchestrator_service/app/consumers/*stage_consumer.py`
- `tests/unit/services/valuation_orchestrator_service/consumers/*.py`
- `tests/unit/services/financial_reconciliation_service/test_reconciliation_requested_consumer.py`
- `tests/unit/services/pipeline_orchestrator_service/consumers/test_financial_reconciliation_completion_consumer.py`
