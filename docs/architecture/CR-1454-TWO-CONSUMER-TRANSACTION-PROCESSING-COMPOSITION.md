# CR-1454: Two-Consumer Transaction Processing Composition

Date: 2026-07-10
Issue: #468
Status: Hardened locally

## Objective

Compose the final transaction-processing consumer topology without activating it or running it
beside the six legacy compatibility consumers.

## Change

Added `app/runtime/consumer_composition.py` with one final-name builder:

`build_transaction_processing_consumers()`

It constructs exactly:

1. `TransactionProcessingConsumer` on `transactions.persisted`, using group
   `portfolio_transaction_processing_group` and one composed `ProcessTransactionUseCase`;
2. `BookedTransactionReplayRequestConsumer` on `transactions.reprocessing.requested`, using group
   `portfolio_transaction_replay_request_group` and one composed
   `ReplayBookedTransactionUseCase`.

Both use the governed bootstrap servers and current shared consumer DLQ. Explicit use-case and
consumer-factory injection supports isolated tests without transport or infrastructure startup.
Dependency selection uses `is not None`, so valid injected collaborators are never replaced because
of custom boolean semantics.

## Complexity And Runtime Impact

The target topology has two transport loops instead of the current six:

- one normal loop owns atomic cost, cashflow, and position derivation;
- one replay-request loop owns operator-triggered canonical republication.

Each application use case is composed once per process. Database sessions and units of work remain
per message. Replay remains separate because its request topic, consumer lag, throttling, and
operator recovery controls differ from normal booking; it does not justify another deployable.

The runtime manager still defaults to `build_legacy_transaction_consumers()`. This slice therefore
does not add duplicate processing, change offsets, activate new groups, or alter deployed resource
usage.

## Compatibility

No topic payload, event, consumer group currently in use, offset, stage gate, database schema,
public API, image, deployment manifest, README, or wiki behavior changed. The new groups begin only
during the governed atomic cutover after replay, ordering, backlog, load, observability, and rollback
evidence passes.

No wiki update is required because deployed topology remains the six-consumer compatibility host.

## Validation

- target transaction-processing unit pack: 58 passed;
- composition proves exactly two consumers, canonical topics/groups/prefixes, shared DLQ, explicit
  collaborator preservation, and one-time use-case construction;
- focused MyPy and Ruff passed;
- in-process, dependency-inversion, transaction-replay, Vulture source, architecture docs, and diff
  gates passed.
