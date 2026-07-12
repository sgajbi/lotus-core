# CR-1455: Duplicate Booked Transaction Replay Parity

Date: 2026-07-10
Issue: #468
Status: Hardened locally

## Objective

Prove that repeated operator replay requests for one canonical transaction remain financially
idempotent when Kafka assigns distinct offsets, while preserving required downstream compatibility
republication and delivery audit evidence.

## Scenario

The PostgreSQL integration scenario:

1. persists one canonical `ADJUSTMENT` transaction and its portfolio;
2. invokes the canonical replay use case twice with the same transaction and correlation IDs;
3. captures two publications to `transactions.persisted` with the portfolio key and correlation
   header;
4. processes those publications through the combined application path using distinct Kafka event
   IDs;
5. verifies final database state and compatibility outbox effects.

Distinct event IDs are essential: this proves semantic module behavior rather than merely hitting
the aggregate transport-event idempotency fence.

## Proven Invariants

- both replay requests return `REPLAYED` and each confirms producer delivery;
- both canonical payloads preserve transaction identity, portfolio partition key, and correlation;
- both delivery attempts are recorded by the combined processing service;
- one cashflow row and one `CashflowCalculated` event exist because cashflow semantic identity
  suppresses duplicate financial output;
- one final position-history row exists; position replay deterministically replaces/rebuilds the
  affected date range rather than appending duplicate state;
- one `ProcessedTransactionPersisted` compatibility event is emitted per replay attempt so current
  downstream replay consumers are intentionally retriggered.

The third outbox row in this scenario is therefore required compatibility behavior, not duplicate
financial state. Removing it before downstream migration would silently break replay consumers.

## Complexity And Compatibility

No production code, topic, payload, group, schema, API, or runtime topology changed. This slice adds
evidence for the already-composed replay and normal application paths. The compatibility outbox
event remains until the downstream and stage-gate migration is complete.

No README or wiki update is required because deployed topology and operator behavior are unchanged.

## Validation

- PostgreSQL duplicate replay integration scenario: 1 passed in 54.15 seconds;
- focused Ruff and diff checks passed.
