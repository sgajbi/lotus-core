# CR-1664 Outbox Ordered-Stream Claim Fence

## Objective

Preserve durable Kafka ordering when multiple `OutboxDispatcher` instances share the same
`outbox_events` table.

## Finding

`FOR UPDATE SKIP LOCKED` prevented two dispatchers from claiming the same row, but it did not
reserve the row's `(topic, partition_key)` stream. After one dispatcher leased the oldest row, a
competing dispatcher could skip that lock and lease the next row for the same Kafka key. Network
or broker timing could then publish the later event first.

The same defect pattern affected every runtime embedding the shared dispatcher. It was not limited
to one producer service or event family.

Late review also proved that dispatcher recovery did not own its producer boundary. Production
dispatchers used the same cached producer wrapper as replay, direct event, and consumer DLQ
publishers in the process. Purging ambiguous outbox records after a flush exception could therefore
purge an unrelated direct publication and let its caller observe a misleading empty flush.

## Correction

- Define the stream head as the oldest unresolved `PENDING` or `FAILED` row by
  `(created_at, id)` for one `(topic, partition_key)`.
- Claim only eligible stream heads, with at most one event per stream in a batch.
- Keep active leases, future retry windows, and terminal failures as stream-local barriers.
- Continue claiming different keys or topics in parallel.
- Drain another batch immediately after productive work, avoiding a poll-interval delay between
  successive events in a busy stream.
- Fence the producer through its configured Kafka `delivery.timeout.ms` before treating a flush as
  complete. Require the claim lease to exceed that fence by a safety margin, preventing an expired
  publisher from delivering an old stream head after a reclaimed head has released the tail.
- If `flush(...)` raises with ambiguous queued records, purge both queued and in-flight records,
  drain their callbacks, and replace the underlying producer before releasing any row for retry.
  If purge confirmation fails, retain the database claims by aborting result persistence.
- Give every production dispatcher a fresh, non-cached producer. Keep replay, direct event, and DLQ
  publishers on their separate shared producer so dispatcher recovery cannot purge their records.
- Guard every production `OutboxDispatcher` composition against shared-producer construction.
- Add a partial lookup index over unresolved stream order.

Kafka publication remains outside the claim transaction and result writes remain claim-token
fenced. This preserves the existing short-transaction and at-least-once delivery posture.

## Compatibility

Event schemas, payloads, topics, partition counts, producer keys, public APIs, and retry budgets are
unchanged. The claim-lease default increases from 60 to 130 seconds so it safely exceeds the
default 120-second Kafka delivery timeout plus the delivery fence and safety margin. A configured
lease shorter than the producer-specific minimum now fails dispatcher construction. The intentional
behavior change prevents later same-stream publication while an earlier event is pending, leased,
retry-waiting, failed, or still capable of broker delivery. A terminal failed head must be reviewed
and governed-requeued before that stream advances. A flush exception now resets the underlying
producer before rows become retryable; this changes only failure recovery, not successful publish
behavior or event contracts. Each dispatcher-owning service process now maintains one additional
Kafka producer connection for the exclusive outbox recovery boundary.

Mixed dispatcher versions are unsafe because an old process does not honor the stream-head
barrier. Deployments must quiesce all dispatcher-owning workers, apply migration
`c129b2c3d502`, then start only the new version.

## Evidence

- Pre-change deterministic PostgreSQL proof: competing dispatcher claimed same-stream sequence 2
  while sequence 1 had an active lease.
- Corrected proof covers active claims, same-timestamp `id` ordering, retry-waiting and terminal
  barriers, independent keys, topic isolation, lease/delivery-timeout validation, and producer
  flush fencing.
- Flush-exception proof covers successful producer purge/replacement before retry release and
  fail-closed claim retention when purge confirmation fails.
- Producer-ownership proof covers distinct dispatcher/shared wrappers, recovery isolation for an
  already-queued direct publication, every production runtime composition, and a source guard
  rejecting cached-producer dispatcher wiring.
- Final focused, migration, protected CI, exact-main, and operational evidence is recorded on
  issue #795.
