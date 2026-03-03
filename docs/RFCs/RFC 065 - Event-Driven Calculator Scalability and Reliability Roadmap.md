# RFC 065 - Event-Driven Calculator Scalability and Reliability Roadmap

## Status
In Progress (Phase 1 hardening underway)

## Date
2026-03-03

## Owners
- lotus-core: calculator pipeline and canonical processing contracts
- lotus-platform: governance and operational standards

## 1. Summary
This RFC defines a structured, incremental plan to scale lotus-core calculators for high processing load while preserving financial correctness, determinism, and operational reliability.

The design leverages event-driven architecture as the primary scaling model: partitioned workload distribution, independent consumer-group scaling per calculator, idempotent processing, backlog-aware autoscaling, and robust replay/operations controls.

## 2. Goals
1. Support materially higher ingestion and calculation throughput without correctness regressions.
2. Maintain deterministic ordering where financially required.
3. Scale each calculator independently based on its own backlog and latency profile.
4. Improve failure isolation, replay safety, and operational visibility.
5. Deliver improvements in controlled phases with measurable acceptance criteria.

## 3. Non-Goals
1. Re-architect all calculators in a single release.
2. Move performance/risk analytics calculations into lotus-core.
3. Introduce non-canonical naming or cross-service vocabulary drift.

## 4. Partitioning Strategy (Decision)

### 4.1 Approved default model
Your proposal is directionally correct and should be the baseline:

1. Transaction processing partition key: `portfolio_id`
2. Position-level derived processing partition key: `portfolio_id + instrument_id`
3. Portfolio rollups partition key: `portfolio_id`

### 4.2 Why this is correct
1. Portfolio-level transaction ordering preserves accounting integrity for related events:
- buys/sells and associated cash
- corporate actions affecting lots/cost basis
- transfers and ledger-linked adjustments
2. Position-level fan-out enables high parallelism after transaction-state consistency is established.
3. Rollup-by-portfolio aligns naturally with NAV/exposure aggregation outputs.

### 4.3 Required refinements
1. Define deterministic tie-break order inside a partition:
- business date/effective timestamp
- transaction timestamp
- ingestion sequence/event id
2. Add skew controls for very large portfolios:
- backlog-aware worker autoscaling
- optional sub-partition strategy for replay-only flows if needed
3. Preserve strict per-key ordering only where required; allow wider parallelism for stateless enrichment tasks.

## 5. Target Operating Model

### 5.1 Topic and consumer-group boundaries
1. Isolate calculators in separate consumer groups:
- position
- cost
- valuation
- cashflow
- timeseries
2. Keep domain-event topics immutable/canonical; introduce dedicated derived topics when needed for heavy stages.

### 5.2 Idempotency and write safety
1. Every consumer must be idempotent by event identity + version.
2. State writes must be compare-and-set/upsert safe.
3. Job transitions must be atomic and epoch/version fenced.

### 5.3 Backpressure and workload classes
1. Split hot path vs heavy path:
- hot path: transaction-to-state correctness updates
- heavy path: historical rebuild/recompute
2. Introduce explicit backlog controls and prioritization.

### 5.4 Replay and failure management
1. Standard dead-letter queues with deterministic failure codes.
2. Replay tools by key/date range with auditable execution metadata.

## 6. Incremental Delivery Plan

### Phase 0 - Baseline instrumentation and SLOs
1. Establish per-calculator SLOs:
- consumer lag
- lag age seconds
- end-to-end processing latency
- failure/retry rate
2. Add dashboards and alert thresholds.

Acceptance:
1. SLO dashboard exists for each calculator.
2. On-call runbook includes lag spike and stuck-partition handling.

### Phase 1 - Partitioning and ordering hardening
1. Enforce partition-key standards in producer and consumer contracts.
2. Implement deterministic in-partition ordering tie-breaks.
3. Validate no ordering regressions via characterization tests.

Acceptance:
1. Deterministic outcomes under shuffled ingestion order.
2. No duplicate accounting side-effects in replay tests.

### Phase 2 - Independent scaling controls
1. Configure autoscaling per calculator group using lag/latency metrics.
2. Apply min replicas and burst profile per workload class.
3. Tune fetch/batch/commit settings per calculator.

Acceptance:
1. Sustained high-load run meets SLOs.
2. No cross-calculator starvation.

### Phase 3 - Backpressure, DLQ, and replay reliability
1. Add standardized DLQ policy with reason-code taxonomy.
2. Add replay controls with rate limiting and blast-radius guardrails.
3. Add backlog-threshold controls for non-critical workloads.

Acceptance:
1. Poison events isolated without pipeline collapse.
2. Replay completion is deterministic and auditable.

### Phase 4 - Throughput optimization
1. Introduce safe micro-batching for heavy writes.
2. Tune DB indexes and query plans for bottleneck paths.
3. Reduce job-table contention with optimized claim/update patterns.

Acceptance:
1. Measured throughput uplift versus Phase 0 baseline.
2. No correctness drift under concurrency stress tests.

### Phase 5 - Production hardening and governance closeout
1. Document operating envelopes and scaling playbooks.
2. Add CI smoke/load checks for key contracts.
3. Final architecture review and governance sign-off.

Acceptance:
1. All required checks green.
2. Operations team runbook approved.

## 7. Test Strategy
1. Unit tests for idempotency and ordering logic.
2. Integration tests for end-to-end event flow across calculators.
3. Concurrency and replay tests (duplicate, delayed, out-of-order events).
4. Load tests by workload profile (steady-state and burst).

## 8. Risks and Mitigations
1. Hot-key skew on large portfolios
- Mitigation: autoscaling + backlog controls + replay-specific partition strategy
2. Hidden ordering dependencies across calculators
- Mitigation: explicit contracts and characterization tests
3. Retry storms
- Mitigation: bounded retries, DLQ policies, exponential backoff
4. Job-table contention
- Mitigation: claim strategy tuning, index optimization, batch updates

## 9. Open Decisions
1. Maximum acceptable lag age by calculator under peak load.
2. Replay isolation policy (shared workers vs dedicated workers).
3. Partition count growth strategy and rebalancing procedure.

## 10. Definition of Done
1. All phases completed or formally deferred with rationale.
2. SLOs consistently met in load and replay scenarios.
3. No financial correctness regressions in characterization suites.
4. Full operational runbook and monitoring coverage in place.

## 11. Implementation Progress (2026-03-03)

### Completed in this change set
1. Partition-key hardening at ingestion publish boundary:
- transaction publish now rejects empty `portfolio_id` partition keys
- transaction partition keys are normalized (`strip`) before Kafka publish
2. Deterministic replay ordering hardening:
- added canonical transaction ordering function with explicit tie-breaks:
  - effective business date (derived from transaction timestamp)
  - transaction timestamp
  - ingestion timestamp (`created_at`) when available
  - transaction id
- position replay now uses deterministic ordering key
- replay query ordering no longer uses surrogate DB id as tie-break; uses `transaction_id`
3. Persistence safety update:
- transaction UPSERT now excludes `None` values to prevent nullable event fields
  from clobbering non-null DB defaults

### Validation coverage added
1. Unit tests for transaction partition-key guardrails in ingestion service
2. Unit tests for deterministic transaction ordering helper
3. Unit test for deterministic ordering in backdated replay flow

### Phase 2 progress (2026-03-03)
1. Added environment-driven Kafka consumer tuning:
- global defaults via `LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON`
- per-consumer-group overrides via `LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON`
- strict key whitelist and type coercion to prevent unsafe runtime config
2. Applied runtime tuning automatically in `BaseConsumer` for every service consumer group.
3. Added autoscaling deployment artifacts:
- KEDA `ScaledObject` definitions for core calculator consumer groups
- runbook-style usage notes and tuning guidance
