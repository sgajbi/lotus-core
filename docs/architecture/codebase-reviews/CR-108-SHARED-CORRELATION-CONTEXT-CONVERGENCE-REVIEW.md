# CR-108: Shared Correlation Context Convergence Review

Date: 2026-03-12
Status: Hardened

## Problem

After earlier direct-path correlation fixes, two high-value consumers still carried hand-rolled correlation setup instead of using the shared helper:

- `PriceEventConsumer`
- `TransactionEventConsumer`

They already behaved correctly, but they implemented the same contract differently:

- manual fallback construction
- manual `ContextVar` token management

That left the direct-consumer correlation contract correct in outcome but inconsistent in implementation, which increases drift risk.

## Fix

Updated:

- `src/services/valuation_orchestrator_service/app/consumers/price_event_consumer.py`
- `src/services/calculators/position_calculator/app/consumers/transaction_event_consumer.py`

Both consumers now use `BaseConsumer._message_correlation_context(...)` instead of hand-rolled context setup.

This keeps:

- header correlation resolution
- payload fallback handling
- deterministic fallback behavior
- context reset behavior

on the same shared path used by the other direct-invocation consumers hardened in CR-095 through CR-107.

## Proof

Validated against the existing direct-path unit coverage:

- `tests/unit/services/valuation_orchestrator_service/consumers/test_price_event_consumer.py`
- `tests/unit/services/calculators/position_calculator/consumers/test_position_calculator_consumer.py`

Result:

- `14 passed`

## Follow-up

For direct Kafka consumer paths, shared helper convergence is now the standard:

- do not hand-roll `correlation_id_var` setup
- use `_message_correlation_context(...)`

This keeps the direct-path contract uniform and reduces drift between services.
