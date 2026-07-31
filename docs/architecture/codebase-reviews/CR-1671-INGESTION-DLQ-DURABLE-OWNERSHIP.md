# CR-1671 Ingestion DLQ Durable Ownership And Recovery

## Scope

GitHub issues #862 and #863. This review supersedes CR-1294's unsafe
latest-by-correlation compatibility rule while retaining its bounded-query improvement.

## Findings

1. `correlation_id` was non-unique but controlled DLQ membership and replay candidate ownership.
2. downstream outbox hops did not retain the originating ingestion job.
3. evidence gates treated every processing DLQ as unresolved after successful replay.
4. replay posture used a global timestamp maximum instead of deterministic per-event history.
5. a later `duplicate_blocked` row erased older equivalent success, while truncated history could
   overclaim recovery.

## Correction

1. Added message-scoped `ingestion_job_id` ownership across ingestion/replay publish, Kafka
   consumers, outbox persistence/dispatch, and consumer-DLQ persistence.
2. Added migration `c133b2c3d506` with unique-only legacy backfill, a nullable DLQ ownership foreign
   key, indexed `(ingestion_job_id, observed_at DESC, id DESC)` reads, and indexed deterministic
   replay-audit ordering.
3. Replaced evidence correlation membership with bounded job-owner membership plus exact replay
   event linking, and removed the now-dead DLQ-by-correlation service/query compatibility seam.
4. Replaced latest-correlation replay selection with owner-first selection and a unique-only
   bounded legacy fallback.
5. Added a pure per-event recovery policy. `replayed` proves recovery; later equivalent
   `duplicate_blocked` preserves proven success; later failure, bookkeeping failure, dry-run-only
   history, missing proof, or truncated evidence remains unresolved.
6. Retained immutable DLQ and replay-audit rows in the evidence response.

## Compatibility

Route paths, request shapes, status codes, replay fingerprints, and immutable evidence history are
unchanged. `ConsumerDlqEventResponse.ingestion_job_id` is additive. Existing legacy rows retain
single-job compatibility through unique-only backfill/fallback; ambiguous correlation reuse now
fails closed instead of selecting an unrelated latest job.

No runtime service split, topic change, partition change, or supported-feature posture change was
needed. Event-replay application policy owns recovery semantics; ingestion stores and shared event
infrastructure own persistence and propagation.

## Validation

1. 217 focused unit tests passed across policy, replay, evidence, stores, publishers, consumers,
   outbox, and migration shape.
2. 1 PostgreSQL round-trip test passed in 49.15 seconds, proving unique/ambiguous backfill isolation,
   foreign-key enforcement, indexes, rollback, and reapply.
3. `make migration-smoke` passed with single Alembic head `c133b2c3d506`.
4. Event-runtime, OpenAPI, architecture, and MyPy gates passed; MyPy checked 240 source files.
5. Wiki/docs gates, strict wiki quality, and pre-merge unpublished-source parity check passed.
6. Scoped Ruff and `git diff --check` passed.

## Delivery Status

Implementation is fixed locally in signed commits `e1501db2a`, `74c42f7bd`, `45457066e`, and
`0d812f97b`. Protected PR CI,
exact-main validation, wiki publication/parity, GitHub evidence updates, and verified issue closure
remain required before completion.
