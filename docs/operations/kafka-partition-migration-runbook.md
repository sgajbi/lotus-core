# Kafka Partition Migration Runbook

## Purpose

Use this runbook when a deployed Kafka topic does not match
`contracts/eventing/kafka-topic-runtime-contract.v1.json`.

Core services fail startup when an existing governed topic has a different partition count. This
is intentional: starting against an unreviewed topology can break domain ordering even when event
schemas and payloads are unchanged.

## Current Transaction Cutover

The governed contract increases only these transaction paths from `8` to `12` partitions:

- `transactions.raw.received` with `persistence_group_transactions`;
- `transactions.persisted` with `portfolio_transaction_processing_group`.

Both consumer groups have `max_in_flight_messages=12` and retain
`per_key_concurrency=1`. All producers use `portfolio_id|security_id`, so same-position events stay
ordered while independent positions can use the additional capacity. Do not increase only the
topic or only the consumer profile.

The exact-source fan-in artifact `20260717T003225Z` reduced drain from `110.249s` to `95.247s`
(`13.61%`) with exact reconciliation, attempts `2/2`, zero repeats/failures, peak active database
connections `11`, and peak lock waiters/blocked sessions `2/2`. Twelve is deliberately below the
service's default maximum pool capacity of fifteen connections. A further increase requires fresh
pool, lock, lag, CPU, and exact-daily evidence.

## Ordering Invariants

- Kafka ordering is guaranteed only within one partition.
- Dates and epochs are not partition-key components. Backdated events, corrections, reversals, and
  restatements must remain on the same business stream as the original state.
- Transaction ingestion, persistence, replay, and economics are portfolio-security ordered.
  Backdated arrivals rebuild deterministic position timelines. Cross-security corporate-action and
  linked-leg correctness is enforced by explicit dependency references, deterministic domain
  ordering, reconciliation, and portfolio-security mutation locks rather than portfolio-wide
  transport serialization.
- Valuation and position timeseries work is portfolio-security ordered.
- Market prices are security ordered, FX rates are directed-currency-pair ordered, and business
  dates are calendar ordered.
- Transaction reprocessing requests resolve `portfolio_id` from the authoritative transaction
  ledger before publication and are portfolio ordered. Unknown transactions are rejected before
  Kafka publication.
- Current event contracts do not carry source-owned tenant identity. Do not add a synthetic tenant
  component or describe the current keys as tenant-isolation proof.

## Pre-Cutover Evidence

1. Record the contract version, application image digest, Git SHA, broker cluster identity, and
   affected topic metadata.
2. Capture consumer group assignments, committed offsets, high watermarks, lag, and any active
   replay or repair jobs.
3. Stop new producer traffic for affected topics.
4. Allow consumers and the outbox dispatcher to drain. Require zero source-topic lag, no in-flight
   messages, and no pending or failed outbox rows for the affected event family.
5. Stop affected consumers before changing topic metadata.
6. Take database and broker recovery checkpoints under the environment's normal backup controls.

Do not use a live partition increase while old-partition lag remains. Kafka may map the same key to
a different partition after the count changes, so old and new records for one domain key can be
processed concurrently during an unbounded live expansion.

## Fresh Environment

For a new broker, run the normal `kafka-topic-creator` prerequisite. It creates every missing topic
with its source-owned count and fails if any existing topic conflicts with the contract.

```bash
docker compose up -d kafka
docker compose run --rm kafka-topic-creator
```

Verify every active topic against the machine-readable contract before starting application
services.

## Existing Topic Has Fewer Partitions

After pre-cutover drain and shutdown:

1. Increase the topic to the governed count with the approved Kafka administration path.
2. Verify the exact count and broker acknowledgement.
3. Start one consumer instance first and verify assignment, readiness, logs, and committed offsets.
4. Resume producers with a bounded canary workload.
5. Verify same-key serialization, independent-key concurrency, lag recovery, database lock/pool
   behavior, outbox health, reconciliation, and support evidence.
6. Increase replicas only up to the governed partition capacity.

Historical records remain in their original partitions. The mandatory zero-lag cutover prevents
those consumed records from racing with new records that may hash to different partitions.

## Existing Topic Has More Partitions

Kafka cannot reduce a topic's partition count in place.

- In local non-authoritative environments, stop the stack and recreate only the disposable Kafka
  data volume before running `kafka-topic-creator` again.
- In shared, test, staging, or production environments, do not delete or recreate the topic. Keep
  affected services stopped and deliver a versioned replacement-topic migration with producer and
  consumer cutover, offset/evidence mapping, downstream coordination, and explicit rollback.
- Do not weaken startup verification or change the source contract merely to match accidental
  broker state.

## Rollback

Partition increases cannot be reversed on the same topic. Before resuming full traffic, define a
rollback point that can:

1. pause producers again,
2. drain and stop consumers,
3. restore database state when the canary changed durable calculations,
4. return producers and consumers to the pre-approved topic or versioned replacement topology,
5. restore recorded offsets only through the governed offset procedure, and
6. rerun reconciliation and duplicate-delivery checks.

Never reset offsets without preserving the transaction semantic fences, valuation epochs, outbox
identity, and replay audit evidence that make redelivery safe.

## Completion Evidence

- topic metadata matches the source contract,
- all required services pass startup/readiness checks,
- no same-domain-key overlap is observed,
- shutdown drains and commits all accepted work,
- duplicate, poison, restart, backdated correction, reversal, restatement, and corporate-action
  scenarios reconcile,
- p50/p95/p99 latency, lag, database locks/pool, CPU, memory, and outbox evidence are recorded, and
- the 100,000-transaction certification profile passes before production promotion.
