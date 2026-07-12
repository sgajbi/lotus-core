# CR-1450: Booked Transaction Replay Application Boundary

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Give the final transaction-processing deployable one framework-neutral application boundary for
replaying a canonical booked transaction without carrying legacy consumer infrastructure into the
use case.

## Finding

The compatibility `ReprocessingConsumer` owns JSON/Kafka parsing, correlation context, SQLAlchemy
session acquisition, Kafka producer lookup, repository construction, replay invocation, retry
classification, and DLQ behavior. Reusing it as the target application boundary would preserve the
same mixed ownership under a new package.

## Change

Added:

- `ReplayBookedTransactionCommand`, which normalizes and requires a transaction id;
- `BookedTransactionReplayStatus` with explicit `REPLAYED` and `NOT_FOUND` states;
- `ReplayBookedTransactionResult`;
- `ReplayBookedTransactionUseCase`;
- `BookedTransactionReplayPort`.

The application use case knows only that a canonical booked transaction is requested and whether
the port replayed it. It does not import Kafka messages, SQLAlchemy, shared repository
implementations, producer clients, retry libraries, or framework exceptions.

## Compatibility

No topic, group, payload, correlation, retry, DLQ, repository, publication, runtime, image, schema,
or public API behavior changed. The target use case is not registered yet.

## Validation

- replayed/not-found and blank-id tests: 3 passed;
- focused MyPy and Ruff passed;
- in-process boundary and diff checks passed.

No README/wiki change is required because deployed replay behavior and topology are unchanged.
