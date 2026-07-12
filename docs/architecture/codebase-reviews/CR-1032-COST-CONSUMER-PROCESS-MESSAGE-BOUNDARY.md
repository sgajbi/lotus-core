# CR-1032: Cost Consumer Process Message Boundary

Date: 2026-06-05

## Scope

Reduce cost calculator consumer process-message complexity while preserving Kafka payload decoding,
event-id derivation, correlation propagation, Pydantic validation, database transaction handling,
idempotency claiming, portfolio/instrument lookup, transaction preparation, event construction,
outbox publication, retry behavior, retry metrics, DLQ behavior, and failure metrics.

## Finding

`CostCalculatorConsumer.process_message` mixed message metadata extraction, JSON parsing,
correlation context setup, event validation, database-session iteration, transaction-scoped
repository setup, idempotency, portfolio/instrument reads, event preparation, cost-engine event
building, emitted-event construction, outbox publication, and four exception outcome families in
one C-ranked method.

## Action

Added focused helpers for message value/event-id extraction, valid cost-event processing,
process-message error classification, and process-message failure metric recording. The public
retry-decorated method remains the Kafka entry point and delegates transaction-scoped processing and
error outcomes.

## Result

`CostCalculatorConsumer.process_message` improved from `C (11)` to `A (2)`, and `consumer.py`
remains A-ranked maintainability at `A (22.35)`. Follow-up remains to reduce the remaining
B-ranked cost consumer helpers by measured risk.

## Evidence

- `python -m pytest tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py -q`
  => 26 passed
- `python -m ruff check src\services\calculators\cost_calculator_service\app\consumer.py tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py`
  => all checks passed
- `python -m ruff format src\services\calculators\cost_calculator_service\app\consumer.py tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py`
  => 1 file reformatted, 1 file left unchanged
- `python -m radon cc src\services\calculators\cost_calculator_service\app\consumer.py -s`
  => `CostCalculatorConsumer.process_message` `A (2)`
- `python -m radon mi src\services\calculators\cost_calculator_service\app\consumer.py -s`
  => `consumer.py` `A (22.35)`
- `python -m radon raw src\services\calculators\cost_calculator_service\app\consumer.py`
  => 659 SLOC / 312 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal cost calculator consumer refactor that
preserves existing retry, transaction processing, outbox, metrics, and DLQ semantics.
