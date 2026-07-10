# CR-1453: Booked Transaction Replay Request Delivery

Date: 2026-07-10
Issue: #468
Status: Hardened locally

## Objective

Replace the legacy replay consumer's mixed transport, application, repository, session, producer,
retry, and DLQ responsibilities with one explicit delivery boundary for the target combined
transaction-processing deployable.

## Change

Added:

- immutable `BookedTransactionReplayRequest` delivery DTO and one JSON request mapper;
- `BookedTransactionReplayRequestConsumer`, which invokes only
  `ReplayBookedTransactionUseCase`;
- application-owned dependency-unavailable and invariant-violation errors so SQLAlchemy and Kafka
  implementation failures do not leak through the delivery/application contract;
- infrastructure mapping from database and canonical replay-publication failures to the retryable
  application error;
- read-only unit-of-work capability properties, correcting the port contract to match the concrete
  transaction-scoped implementation.

The mapper trims identifiers and requires supported transaction/correlation identifiers to be
strings. It deliberately rejects legacy implicit coercion of arrays, objects, booleans, or numbers
into identifiers because those shapes are outside the event contract and create ambiguous replay
targets. Header correlation remains authoritative, with payload correlation as fallback.

## Delivery Outcomes

| Outcome | Behavior |
|---|---|
| Canonical transaction replayed | Acknowledge and log `replayed`. |
| Canonical transaction not found | Acknowledge with a bounded warning. |
| Missing or blank transaction ID | Preserve legacy behavior: acknowledge with a bounded warning. |
| Database or replay publication unavailable | Raise `RetryableConsumerError`; shared retry budget owns retry, exhaustion, DLQ, and offset handling. |
| Invalid JSON, non-object payload, non-string identifier, or impossible replay cardinality | Propagate as terminal; shared consumer handling owns DLQ and offset handling. |

This removes the legacy consumer's nested retry decorator and direct DLQ publication from the
target path. One policy now owns retry exhaustion and terminal routing.

## Runtime And Performance

The mapper performs one bounded JSON decode. The consumer adds no service hop, producer, database
session, or transaction beyond the composed replay adapter. A replay request still republishes one
canonical transaction to `transactions.persisted`, where the combined normal consumer applies the
atomic cost, cashflow, and position use case.

## Compatibility

Topic, valid payload shape, correlation precedence, missing-ID acknowledgement, and not-found
acknowledgement are preserved. Unsupported non-string identifier coercion is intentionally removed
from the target path and covered by terminal-payload tests. Retry implementation is intentionally
simplified to the repository-wide bounded consumer policy; this avoids stacked retry loops while
retaining eventual DLQ recovery.

The target consumer is not registered yet, so deployed runtime, group, image, manifests, OpenAPI,
README, and wiki truth remain unchanged. No wiki update is required for this local non-runtime
slice.

## Validation

- target transaction-processing unit pack: 56 passed;
- replay request mapping/delivery covers replayed, not found, missing ID, header/payload
  correlation, malformed payload, retryable dependency failure, and terminal invariant failure;
- adapter tests cover database and replay-publication error translation;
- focused MyPy, Ruff, Ruff format, Vulture source, in-process boundary, and diff checks passed.
