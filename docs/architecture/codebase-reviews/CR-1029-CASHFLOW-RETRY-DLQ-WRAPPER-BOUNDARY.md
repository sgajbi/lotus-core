# CR-1029: Cashflow Retry DLQ Wrapper Boundary

Date: 2026-06-05

## Scope

Reduce cashflow calculator retry/DLQ wrapper complexity while preserving Kafka message metadata
derivation, JSON decoding, correlation fallback, Pydantic event validation, database-session
iteration, retry behavior for integrity errors, invalid-payload DLQ behavior, missing-rule DLQ
behavior, linked-cash-leg DLQ behavior, and unexpected-error DLQ behavior.

## Finding

After CR-1028, `CashflowCalculatorConsumer._process_message_with_retry` still mixed message key
decoding, payload decoding, event-id construction, correlation-context setup, Pydantic validation,
database-session iteration, validated-event processing, and five retry/DLQ exception outcomes in
one B-ranked retry wrapper.

## Action

Added focused helpers for message key/value/event-id extraction, decoded cashflow event processing,
and cashflow processing error classification. The retry-decorated method remains the retry wrapper
while delegating decoded event orchestration and exception-specific DLQ handling.

## Result

`CashflowCalculatorConsumer._process_message_with_retry` improved from `B (8)` to `A (2)`. Every
function/class/method in `transaction_consumer.py` now reports A-ranked cyclomatic complexity, and
the module remains A-ranked maintainability at `A (33.48)`.

## Evidence

- `python -m pytest tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py -q`
  => 21 passed
- `python -m ruff check src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py`
  => all checks passed
- `python -m ruff format src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py`
  => 1 file reformatted, 1 file left unchanged
- `python -m radon cc src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py -s`
  => `_process_message_with_retry` `A (2)` and every function/class/method A-ranked
- `python -m radon mi src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py -s`
  => `transaction_consumer.py` `A (33.48)`
- `python -m radon raw src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py`
  => 486 SLOC / 240 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal cashflow calculator consumer refactor that
preserves existing retry and DLQ classification semantics.
