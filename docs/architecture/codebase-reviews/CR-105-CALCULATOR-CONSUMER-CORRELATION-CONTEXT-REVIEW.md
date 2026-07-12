# CR-105: Calculator Consumer Correlation Context Review

Date: 2026-03-12
Status: Hardened

## Problem

Several calculator consumers could be invoked directly in tests or in-process execution paths without going through `BaseConsumer.run()`. Those paths still assumed `correlation_id_var` had already been initialized by the runtime loop.

That meant durable side effects could lose the real Kafka header correlation id even when the message already carried one. The gap was most visible in:

- `cashflow_calculator_service`
- `cost_calculator_service`
- `position_valuation_calculator`

## Why it mattered

These consumers persist outbox events and idempotency records. If direct invocation falls back to `"<not-set>"`, audit lineage degrades even though the message header already contains the correct correlation id.

This is not cosmetic logging drift. It weakens the durable traceability contract for calculator-side processing.

## Fix

Applied `BaseConsumer._message_correlation_context(...)` in the calculator direct consumer paths:

- `src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py`
- `src/services/calculators/cost_calculator_service/app/consumer.py`
- `src/services/calculators/position_valuation_calculator/app/consumers/valuation_consumer.py`

The consumers now resolve the Kafka header correlation id locally when invoked directly and use it consistently for:

- outbox correlation ids
- idempotency `mark_event_processed(...)`

While doing this, the `cost_calculator_service` success path regression was also corrected so `mark_event_processed(...)` executes unconditionally after successful transaction and instrument outbox publication, not only when instrument events exist.

## Proof

Targeted calculator consumer unit coverage now proves direct-path correlation fidelity:

- `tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py`
- `tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
- `tests/unit/services/calculators/position_valuation_calculator/consumers/test_valuation_consumer.py`

Validation:

- `41 passed`

## Follow-up

Any remaining consumer whose `process_message(...)` can be called directly should either:

1. use `_message_correlation_context(...)`, or
2. explicitly document why direct invocation is unsupported

Relying on ambient runtime context for durable audit fields is not acceptable on those paths.
