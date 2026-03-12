# CR-107: Persistence Consumer Correlation Context Review

Date: 2026-03-12
Status: Hardened

## Problem

`persistence_service` uses a shared `GenericPersistenceConsumer` base class for direct `process_message(...)` handling, idempotency, and optional outbox publication.

That base class still read `correlation_id_var` directly without first establishing local message correlation context. On direct invocation paths, durable writes could therefore fall back to ambient/default correlation state even when the Kafka header already carried the correct `correlation_id`.

## Why it mattered

This affected multiple persistence consumers at once:

- transaction persistence
- instrument persistence
- market-price persistence

The problem was not logging noise. It weakened the durable audit contract for both:

- outbox correlation ids
- idempotency `mark_event_processed(...)`

## Fix

Updated:

- `src/services/persistence_service/app/consumers/base_consumer.py`

The base class now wraps processing in `_message_correlation_context(...)`, using the message header and any payload fallback correlation id when invoked directly outside `BaseConsumer.run()`.

## Proof

Strengthened unit coverage for representative persistence consumers:

- `tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py`
- `tests/unit/services/persistence_service/consumers/test_persistence_instrument_consumer.py`
- `tests/unit/services/persistence_service/consumers/test_persistence_market_price_consumer.py`

Those tests now prove the direct path preserves the header correlation id in both:

- outbox publication
- idempotency records

Validation:

- `7 passed`

## Follow-up

Keep correlation handling centralized in the base class for persistence consumers. Future subtype-specific fixes should not reintroduce ambient-context dependence.
