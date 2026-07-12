# CR-095 Replay Correlation Propagation Review

## Scope

- `position_calculator` replay and stage-gate consumer correlation propagation
- idempotency/audit fidelity on direct `process_message(...)` paths

## Finding

`TransactionEventConsumer.process_message(...)` read `correlation_id_var` directly and
assumed the base Kafka runtime had already populated it. That assumption holds inside
`BaseConsumer.run()`, but it does not hold for direct consumer invocation paths such as
unit tests and any future in-process retry/replay entrypoints that call
`process_message(...)` without first entering the base runtime loop.

As a result, replay-path idempotency records could be written with correlation id
`"<not-set>"` even when the Kafka message headers already carried a real
`correlation_id`.

## Action Taken

- Extracted reusable header resolution into
  `portfolio_common.kafka_consumer.BaseConsumer._resolve_message_correlation_id(...)`
- Updated `TransactionEventConsumer.process_message(...)` to:
  - fall back to Kafka header correlation when the context var is unset
  - set/reset the correlation context locally for the duration of direct processing
- Added consumer-level tests proving both replay and stage-gate paths now persist the
  Kafka header correlation into idempotency state

## Result

Replay and stage-gate direct consumer execution now preserve correlation fidelity
consistently with the main runtime loop. This closes an audit/idempotency trace gap
without changing the live `BaseConsumer.run()` semantics.

## Evidence

- `src/libs/portfolio-common/portfolio_common/kafka_consumer.py`
- `src/services/calculators/position_calculator/app/consumers/transaction_event_consumer.py`
- `tests/unit/services/calculators/position_calculator/consumers/test_position_calculator_consumer.py`
- `python -m pytest tests/unit/services/calculators/position_calculator/consumers/test_position_calculator_consumer.py -q`
- `python -m pytest tests/unit/libs/portfolio-common/test_kafka_consumer.py -q`
