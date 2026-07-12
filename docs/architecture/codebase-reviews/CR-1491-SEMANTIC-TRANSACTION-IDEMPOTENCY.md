# CR-1491: Semantic Transaction Idempotency

Date: 2026-07-11
Issues: #485, #468
Status: Implemented locally; deployment migration and downstream validation pending

## Objective

Prevent an identical booked transaction from repeating cost, cashflow, position, and compatibility
outbox work when it is republished under a different topic, partition, or offset. Reject the same
semantic transaction identity with materially changed content instead of silently skipping or
recalculating it.

## Design

- `BookedTransaction` produces a versioned semantic key from portfolio, transaction, and epoch.
- A canonical SHA-256 fingerprint covers all booked-transaction business fields except
  non-material record creation time. Decimal scale and timezone representations normalize before
  hashing.
- `processed_events` retains physical event identity and gains nullable `semantic_key` and
  `payload_fingerprint` columns. A partial unique index applies only to semantic rows, preserving
  every existing physical-only consumer.
- The combined unit of work classifies claims as `claimed`, `physical_duplicate`,
  `semantic_duplicate`, or `semantic_conflict` before any financial module executes.
- Identical duplicates return the existing `DUPLICATE` processing status. Material conflicts raise
  terminal `transaction_semantic_conflict` for shared DLQ handling unless they arrive through the
  explicit canonical repair workflow.
- A material repair payload claims an immutable `transaction-correction:v1` semantic key containing
  its canonical SHA-256 fingerprint. The original semantic fence and every distinct correction
  remain separate auditable rows; identical correction replay retains the physical repair-delivery
  fence.
- Metrics use the bounded claim outcomes and contain no portfolio or transaction labels.

## Compatibility

The event schema, topic, public API, and ordinary successful result are unchanged. Intentional
behavior changes are that a second identical replay no longer emits another
`ProcessedTransactionPersisted` compatibility event or reruns position processing. Pre-migration
physical fences have null semantic fields and remain valid physical duplicates after deployment.

Standard materially changed deliveries still fail terminally. The existing operational
reprocessing API remains the explicit correction path: its internal repair header permits a new
canonical payload to execute under a payload-specific immutable correction fence instead of being
silently skipped or mutating the original claim.

This supersedes CR-1455's expectation of one compatibility processed event per distinct replay
offset. Replay publication remains auditable at its control boundary; repeated financial-state
processing is not delivery audit evidence.

## Migration And Rollback

Migration `c108b2c3d4ed` adds two nullable columns and one partial unique index. No historical
backfill is required. Downgrade removes the index and columns; application rollback must accompany
schema rollback because the new worker reads and writes those fields.

## Validation

- Semantic identity: `3` deterministic normalization and conflict tests.
- Shared repository/application cohorts: `26` focused tests after legacy-fence correction.
- Unified use case, adapter, consumer, and observability cohort: `21` tests.
- Repository-native transaction-processing contract: `27 passed` in `113.76s` against PostgreSQL
  after rebuilding the migration-runner image.
- Correction extension: `72` focused domain/use-case/position tests, `2` PostgreSQL correction
  tests, repository-native transaction-processing contract `39 passed`, and the correction-to-
  current-valuation E2E scenario passed in `66.59s` after rebuilding the combined runtime image.
- Ruff, MyPy, Alembic single-head, migration contract, architecture boundary, in-process modularity,
  and in-process boundary checks passed.

## Downstream Impact

Consumers may observe fewer duplicate `ProcessedTransactionPersisted` facts during repeated
operator replay. No consumer may rely on duplicate facts as replay audit evidence; use governed
replay audit/control records instead. A materially changed payload under the same semantic key is
now terminal and support-visible rather than silently reprocessed.

No platform skill update is required. Existing backend delivery, issue-resolution, and codebase
review skills already require semantic idempotency, same-pattern scans, compatibility analysis,
and durable context correction. This Core-specific rule is recorded in repository context.
