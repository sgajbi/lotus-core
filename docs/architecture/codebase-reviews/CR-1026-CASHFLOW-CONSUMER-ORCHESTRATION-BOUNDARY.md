# CR-1026: Cashflow Consumer Orchestration Boundary

Date: 2026-06-05

## Scope

Reduce cashflow calculator consumer orchestration complexity while preserving Kafka message
decoding, correlation propagation, idempotency claims, stale replay skipping, epoch fencing,
semantic duplicate suppression, transaction contract validation, non-cash lifecycle skipping,
cashflow calculation, outbox staging, commit/rollback behavior, and DLQ classifications.

## Finding

`CashflowCalculatorConsumer._process_message_with_retry` mixed payload decoding, event validation,
correlation context setup, database transaction management, physical and semantic idempotency,
stale replay detection, epoch fencing, CA Bundle A and linked-cash-leg validation, non-cash
lifecycle filtering, rule lookup, cashflow calculation, outbox event construction, commit/rollback
handling, and retry/DLQ error classification in one D-ranked method.

## Action

Extracted transaction-scoped processing plus focused helpers for physical event claiming, stale
replay detection, semantic event claiming, cashflow transaction contract validation, non-cash
lifecycle classification, required rule lookup, cashflow calculation staging, and
`CashflowCalculatedEvent` construction. The retry method remains the Kafka decoding and DLQ
classification boundary.

## Result

`CashflowCalculatorConsumer._process_message_with_retry` improved from `D (24)` to `B (8)`.
`transaction_consumer.py` remains A-ranked maintainability at `A (37.29)`. Follow-up remains to
reduce `_get_rule_for_transaction` `B (7)` and `_process_validated_cashflow_event` `B (7)` once the
next narrow cashflow consumer slice is selected.

## Evidence

- `python -m pytest tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py -q`
  => 21 passed
- `python -m ruff check src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py`
  => all checks passed
- `python -m ruff format src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py`
  => 1 file reformatted, 1 file left unchanged
- `python -m radon cc src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py -s`
  => `_process_message_with_retry` `B (8)`, `_get_rule_for_transaction` `B (7)`, `_process_validated_cashflow_event` `B (7)`, and all extracted helpers A-ranked
- `python -m radon mi src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py -s`
  => `transaction_consumer.py` `A (37.29)`
- `python -m radon raw src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py`
  => 380 SLOC / 212 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal cashflow calculator consumer refactor that
preserves existing message processing, commit/rollback, and DLQ semantics.
