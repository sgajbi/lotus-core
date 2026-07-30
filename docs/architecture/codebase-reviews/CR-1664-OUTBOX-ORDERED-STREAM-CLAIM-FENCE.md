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

A further lifecycle review found that the default 121-second delivery fence did not fit the
60-second Kubernetes termination grace. Shared supervision could cancel the dispatcher task before
delivery was fenced, while cancellation of its `asyncio.to_thread(...)` coroutine could not stop the
underlying batch thread. Kubernetes could then terminate the process before the thread completed.

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
- Start the delivery lease after stream-head selection so database query latency cannot consume the
  safety margin reserved for claim commit and producer publication.
- If `flush(...)` raises with ambiguous queued records, purge both queued and in-flight records,
  drain their callbacks, and replace the underlying producer before releasing any row for retry.
  If purge confirmation fails, retain the database claims by aborting result persistence.
- Give every production dispatcher a fresh, non-cached producer while retaining the established
  `portfolio_common` producer-policy lookup identity. Keep replay, direct event, and DLQ publishers
  on their separate shared producer so dispatcher recovery cannot purge their records.
- Guard every production `OutboxDispatcher` composition against shared-producer construction.
- Derive a dispatcher supervision timeout from the producer-specific delivery fence plus a drain
  margin, and pass it from every dispatcher-owning runtime to shared shutdown supervision. Shared
  supervision takes the maximum of that fence and every configured consumer drain budget plus its
  grace, so dispatcher safety never shortens a supported consumer shutdown override.
- Require the configured pod termination grace to exceed that supervision budget by a further
  process-termination margin. Fail dispatcher construction for unsafe combinations.
- Increase the governed derived-state and transaction-processing pod grace from 60 to 150 seconds
  and bind `OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS=150` in each deployment.
- Bind `stop_grace_period` for all five dispatcher-owning services in app-local Compose to the same
  termination-grace override exposed through the shared service environment, with a 150-second
  default.
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
The two governed Kubernetes deployments now allow 150 seconds for termination instead of 60.
App-local Compose now allows the same 150 seconds for every dispatcher-owning service instead of
its 10-second default, and an operator override changes both the runtime budget and Compose stop
window together. Exclusive dispatcher producers preserve the existing `portfolio_common` policy
override key; exclusivity is an object-ownership boundary, not a new configuration identity.
Runtime supervision waits 126 seconds for a producer using the default 120-second Kafka delivery
timeout, and dispatcher startup rejects termination grace below 136 seconds. Operator overrides of
Kafka delivery timeout must therefore be paired with a sufficiently large outbox claim lease and
termination grace. These are lifecycle controls only; successful dispatch, message contracts, and
retry semantics are unchanged. A consumer drain budget above the dispatcher fence remains
authoritative and receives its existing one-second completion grace.

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
- Shutdown-fence proof covers runtime budget propagation, fail-closed termination-grace validation,
  and manifest equality between the pod grace and runtime configuration for both governed
  dispatcher deployments.
- Lease-origin proof deterministically advances the dispatcher clock during head selection and
  verifies the durable lease begins from the post-selection instant.
- Final focused, migration, protected CI, exact-main, and operational evidence is recorded on
  issue #795.
