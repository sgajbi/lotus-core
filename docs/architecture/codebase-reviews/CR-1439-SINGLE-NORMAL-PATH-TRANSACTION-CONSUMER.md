# CR-1439: Single Normal-Path Transaction Consumer

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Define the one final normal-path Kafka delivery adapter for booked transactions without registering
it in the runtime before concrete calculation parity is complete.

## Change

- Added `TransactionProcessingConsumer` for `transactions.persisted` delivery.
- Parse and validate each payload once, preserve topic/partition/offset event identity, and propagate
  correlation plus W3C trace context into one `ProcessTransactionCommand`.
- Invoke `ProcessTransactionUseCase` exactly once per delivery attempt.
- Acknowledge stale-epoch rejection only after the atomic use case has rolled back.
- Map retryable application and SQLAlchemy dependency failures to shared consumer retry handling;
  propagate malformed and terminal failures to shared DLQ handling.
- Log source-safe aggregate outcomes and module record/replay counts.

## Performance And Scalability

The target normal path has one JSON/Pydantic parse, one DTO mapping, one use-case call, one database
session, and one commit. Scaling remains partition/replica based with the shared consumer's bounded
in-flight and per-key ordering controls. Separate calculator consumers are not part of the final
normal topology.

## Compatibility

The target consumer is not registered in the manager or deployment manifests. Existing consumers,
topics, groups, retries, DLQs, images, and runtime behavior remain unchanged. Reprocessing remains a
separate use case/consumer in the same future deployable.

## Evidence

- Target-service unit pack: 33 passed.
- Tests cover lineage mapping, single invocation, retryable application failure, retryable database
  failure, stale-epoch acknowledgement, terminal propagation, and malformed payload rejection.
- Delivery MyPy/Ruff, modularity/boundary/strict architecture, full source dead-code, and diff gates
  passed.

## Same-Pattern Decision

Do not register cost, cashflow, or position normal consumers alongside this target consumer at
cutover. Compatibility consumers remain only until canonical output, replay, load, and rollback
evidence permit an atomic topology switch.

No README/wiki change is required because deployed topology has not changed.
