# CR-1452: Booked Transaction Replay Composition

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Provide one governed production composition boundary for the booked-transaction replay use case.

## Change

Added:

- `CanonicalBookedTransactionReplayerFactory`, which creates the shared
  `ReprocessingRepository` for a caller-owned session and shared Kafka producer;
- `build_replay_booked_transaction_use_case(...)`, which composes the replay application use case,
  SQLAlchemy adapter, repository factory, repository-standard session factory, and shared producer.

The builder supports explicit session and producer injection. Producer selection uses an explicit
`is not None` check so a valid injected object is never replaced because of custom boolean
semantics.

## Runtime And Performance

The composition creates the producer once and a database session only when a replay request is
processed. The adapter closes that session after the canonical read/publication operation. No
additional service hop, transaction commit, producer instance, or normal-path consumer is added.

## Compatibility

No topic, group, payload, ordering, correlation, retry, partial-publish, flush, DLQ, runtime, image,
schema, or public API behavior changed. The target replay consumer is not registered yet.

## Validation

- production dependency composition tests: 3 passed;
- focused MyPy and Ruff passed;
- diff check passed.

No README/wiki change is required because deployed replay behavior and topology are unchanged.
