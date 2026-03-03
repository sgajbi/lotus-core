# RFC 065 - Event-Driven Calculator Scalability and Reliability Roadmap

## Status
In Progress (Phase 4 optimization underway)

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

### 5.5 Quantitative variables and sizing model
The following variables are canonical for performance planning, autoscaling thresholds, and runbook decisions:

| Variable | Definition | Unit |
|---|---|---|
| `lambda_in` | Inbound event rate into a calculator consumer group | events/sec |
| `mu_msg` | Sustained per-replica processing throughput | events/sec/replica |
| `N_replica` | Active consumer replicas in a group | replicas |
| `rho` | Utilization ratio = `lambda_in / (N_replica * mu_msg)` | ratio |
| `L_lag` | Current Kafka consumer lag | events |
| `T_lag` | Lag age (`oldest_unprocessed_event_age`) | sec |
| `S_p95` | p95 end-to-end service time per event | sec |
| `B_batch` | Write micro-batch size for heavy persistence steps | records |
| `C_commit` | Offset commit interval or record count boundary | sec or records |
| `R_retry` | Retry attempts for transient failures before DLQ | attempts |
| `T_backoff` | Backoff interval between retries | sec |
| `Q_dlq` | DLQ event rate | events/min |
| `R_replay` | Replay request size (records) | records |
| `J_backlog` | Operational backlog in ingestion control plane (`accepted+queued`) | jobs |

Canonical derived formulas:

| Metric | Formula | Interpretation |
|---|---|---|
| Effective capacity | `Capacity = N_replica * mu_msg` | Max stable throughput before lag growth |
| Headroom | `Headroom = 1 - rho` | Safety margin for burst handling |
| Drain time | `T_drain = L_lag / max(Capacity - lambda_in, epsilon)` | Time to clear lag under current load |
| Replay pressure ratio | `P_replay = R_replay / LOTUS_CORE_REPLAY_MAX_RECORDS_PER_REQUEST` | Guardrail saturation for replay blast radius |
| DLQ pressure | `P_dlq = Q_dlq / Q_dlq_budget` | Incident pressure score for operations |

### 5.6 Numeric operating envelopes (initial baseline)
These are initial target envelopes for Phase 4/5 and should be calibrated with production-like load tests.

| Calculator group | Target `rho` ceiling | Target `T_lag` p95 | Target `S_p95` | DLQ budget |
|---|---:|---:|---:|---:|
| `position` | 0.70 | <= 30 sec | <= 0.20 sec | <= 2 events/15 min |
| `cost` | 0.75 | <= 45 sec | <= 0.35 sec | <= 3 events/15 min |
| `valuation` | 0.75 | <= 60 sec | <= 0.50 sec | <= 3 events/15 min |
| `cashflow` | 0.70 | <= 45 sec | <= 0.30 sec | <= 2 events/15 min |
| `timeseries` | 0.80 | <= 120 sec | <= 1.00 sec | <= 5 events/15 min |

Replay and ingestion-ops safety budgets:

| Control | Baseline value | Source |
|---|---:|---|
| Max replay records per request | 5000 | `LOTUS_CORE_REPLAY_MAX_RECORDS_PER_REQUEST` |
| Max backlog jobs for replay allowance | 5000 | `LOTUS_CORE_REPLAY_MAX_BACKLOG_JOBS` |
| Ingestion write max requests/window | 120 per 60 sec | `LOTUS_CORE_INGEST_RATE_LIMIT_MAX_REQUESTS` / `LOTUS_CORE_INGEST_RATE_LIMIT_WINDOW_SECONDS` |
| Ingestion write max records/window | 10000 per 60 sec | `LOTUS_CORE_INGEST_RATE_LIMIT_MAX_RECORDS` / `LOTUS_CORE_INGEST_RATE_LIMIT_WINDOW_SECONDS` |

### 5.7 Numeric table for autoscaling signal bands
Recommended lag-driven scale bands (to be encoded in KEDA/HPA and runbook alerts):

| Signal band | Condition | Action |
|---|---|---|
| Green | `rho < 0.60` and `T_lag < 15 sec` | Hold baseline replicas |
| Yellow | `0.60 <= rho < 0.80` or `15 sec <= T_lag < 60 sec` | Scale up one band; monitor DLQ pressure |
| Orange | `0.80 <= rho < 0.95` or `60 sec <= T_lag < 180 sec` | Aggressive autoscale; pause non-critical replay |
| Red | `rho >= 0.95` or `T_lag >= 180 sec` | Enter incident mode; block replay except emergency paths |

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

### Phase 3 progress (2026-03-03)
1. Implemented canonical consumer DLQ reason-code taxonomy and persisted it durably:
- added deterministic classifier in `BaseConsumer` for terminal failures
- DLQ payload now includes `error_reason_code` for runbook routing and analytics
- `consumer_dlq_events` now stores `error_reason_code` (indexed) via Alembic migration
2. Exposed reason-code metadata through ingestion operations APIs:
- `ConsumerDlqEventResponse` now includes `error_reason_code`
- ingestion service DLQ event mapping includes new canonical field
3. Added replay blast-radius guardrails:
- replay max-record guardrail (`LOTUS_CORE_REPLAY_MAX_RECORDS_PER_REQUEST`)
- replay backlog guardrail (`LOTUS_CORE_REPLAY_MAX_BACKLOG_JOBS`)
- guardrails enforced for:
  - ingestion job retry replays
  - consumer DLQ correlated replays
  - transaction reprocessing publish endpoint
4. Added meaningful tests:
- DLQ taxonomy and payload reason-code unit tests
- replay guardrail unit tests for record and backlog limits
- ingestion router integration coverage updated for new reason-code field and guardrail methods

### Phase 4 progress (2026-03-03)
1. Reduced ingestion operations query overhead in service hot paths:
- `get_health_summary` now uses one aggregate SQL statement instead of multiple sequential count queries
- `get_consumer_lag` now performs grouped SQL aggregation (`count`, `max`) with DB-side sorting/limit instead of loading and grouping full event sets in Python
2. Added composite indexes for DLQ and replay-audit operational query patterns:
- `consumer_dlq_events(consumer_group, original_topic, observed_at)`
- `consumer_dlq_replay_audit(recovery_path, replay_status, requested_at)`
- `consumer_dlq_replay_audit(replay_fingerprint, replay_status, recovery_path, requested_at)`
3. Added Alembic migration for index rollout to keep runtime behavior and schema in sync.
4. Deepened SQL-side aggregate execution for ingestion operations:
- `get_backlog_breakdown` now uses grouped DB aggregation with conditional counts and backlog oldest-timestamp extraction
- `get_idempotency_diagnostics` now uses grouped DB aggregation (`count`, `count distinct`, `array_agg distinct`, `min/max`) instead of full-row Python grouping
- `get_error_budget_status` now computes current/previous windows via aggregate SQL queries instead of loading job rows
5. Added ingestion-job aggregate indexes for these operations:
- `ingestion_jobs(submitted_at)`
- `ingestion_jobs(status, submitted_at)`
- `ingestion_jobs(idempotency_key, submitted_at)`
6. Optimized SLO computation path:
- `get_slo_status` now uses DB-side aggregate query for total/failure/backlog-age signals and DB percentile (`percentile_cont`) for p95 queue latency
- retained safe fallback path to Python-side p95 calculation for environments without percentile support
7. Added latency-path support index:
- `ingestion_jobs(submitted_at, completed_at)` for p95 latency window scanning efficiency
8. Hardened operational-index coverage for backlog and failure runbooks:
- added partial non-terminal backlog index on ingestion jobs (`status in accepted/queued`) to accelerate stalled/backlog scans
- added ordered failure-history index for ingestion job failures (`job_id, failed_at`) to accelerate runbook failure lookups
9. Correctness and resilience hardening for ops metrics:
- `get_backlog_breakdown.total_backlog_jobs` now reports full-window backlog across all endpoint groups (not only the limited top-N group page)
- narrowed SLO percentile fallback to `SQLAlchemyError` instead of a broad catch-all, reducing risk of masking non-database defects
10. Reduced ingestion job lifecycle transition contention and race windows:
- `mark_queued`, `mark_failed`, and `mark_retried` now use single-statement atomic `UPDATE` paths instead of select-then-mutate flows
- `mark_failed` and `mark_retried` use `UPDATE ... RETURNING` for metric label context (`endpoint`, `entity_type`) without extra reads
- retry counter increments are now DB-atomic (`coalesce(retry_count, 0) + 1`) to avoid lost updates under concurrent retry operations
- added focused unit coverage to lock transition SQL intent and failure-record persistence behavior
11. Added canonical pressure-ratio signals to ingestion error-budget endpoint:
- error-budget response now includes replay backlog pressure ratio and DLQ pressure ratio (`P_dlq`) aligned to RFC formulas
- included raw supporting controls in the same response (`dlq_events_in_window`, `dlq_budget_events_per_window`) for runbook decisions
- added unit and integration coverage to lock new contract fields and calculations
12. Reduced reprocessing job queue contention with atomic claim semantics:
- `ReprocessingJobRepository.find_and_claim_jobs` now uses a single `UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING *` statement
- claim flow now increments `attempt_count` and sets timestamps atomically at claim time
- added composite claim-order index on `reprocessing_jobs(job_type, status, created_at, id)` for hot-path queue scans under load
- added focused unit tests validating SKIP LOCKED SQL shape and row-to-model mapping
13. Added dedicated reprocessing-worker observability signals:
- worker now emits canonical counters for claimed/completed/failed reprocessing jobs
- worker now records batch processing duration histogram for claim/process loop latency tracking
- added focused unit coverage to assert success/failure metric emission paths and timer invocation behavior
14. Hardened valuation-worker queue observability and hot-path indexing:
- valuation repository now emits counters for claimed valuation jobs and stale-job resets
- added focused unit coverage for valuation claim/reset metric emission paths
- added valuation queue indexes for hot operational paths:
  - claim ordering (`status, portfolio_id, security_id, valuation_date, id`)
  - stale-processing scan (`status, updated_at`)

### Phase 5 progress (2026-03-03)
1. Added dedicated RFC-065 operational playbook:
- `docs/operations/RFC-065-Calculator-Scalability-Operations-Playbook.md`
- includes canonical signal definitions, operating bands, incident workflow, replay safety rules, and incident exit criteria
2. Added explicit CI smoke contract coverage for ingestion operations APIs:
- introduced `ops-contract` test suite in `scripts/test_manifest.py`
- wired suite into CI matrix as `Tests (ops-contract)`
- added local runner target `make test-ops-contract`
3. Added canonical operating-band endpoint for automation and runbooks:
- added `GET /ingestion/health/operating-band` to return `green|yellow|orange|red` severity
- classification combines backlog age, DLQ pressure ratio, and SLO breach signals in one response contract
- added unit and integration coverage to lock endpoint behavior and routing shape
4. Refactored operating-band logic into reusable policy + classifier components:
- extracted `OperatingBandPolicy`, `OperatingBandSignals`, and `classify_operating_band(...)`
- centralized threshold policy to avoid duplicated branching logic and simplify future tuning
- added deterministic unit coverage for policy ordering (yellow -> orange -> red)
5. Added ingestion policy introspection endpoint:
- added `GET /ingestion/health/policy` exposing active SLO defaults, replay guardrails, DLQ budget, and operating-band thresholds
- enables runbooks and automation to consume runtime policy directly and avoid configuration drift
- added unit and integration coverage for endpoint contract shape
6. Added deterministic policy-version and fingerprint metadata for drift detection:
- `GET /ingestion/health/policy` now includes `policy_version` and `policy_fingerprint`
- fingerprint is computed from canonical active policy values with stable JSON serialization and SHA-256 truncation
- enables automation to detect runtime policy drift with a single contract read
7. Added reprocessing-queue health endpoint for operations visibility:
- added `GET /ingestion/health/reprocessing-queue` with per-job-type pending/processing/failed counts
- endpoint includes oldest pending age signal for queue pressure triage and worker-scaling decisions
- added unit and integration coverage to lock response contract and aggregation behavior
8. Aligned reprocessing worker tuning with policy introspection:
- `ReprocessingWorker` poll interval and batch size are now env-driven (`REPROCESSING_WORKER_POLL_INTERVAL_SECONDS`, `REPROCESSING_WORKER_BATCH_SIZE`)
- `GET /ingestion/health/policy` now exposes both worker tuning values so automation and runbooks can detect drift
- added focused unit coverage for env override behavior and policy contract fields
9. Extended policy introspection with valuation scheduler runtime tuning:
- `GET /ingestion/health/policy` now exposes `VALUATION_SCHEDULER_POLL_INTERVAL`, `VALUATION_SCHEDULER_BATCH_SIZE`, and `VALUATION_SCHEDULER_DISPATCH_ROUNDS`
- policy fingerprint now includes scheduler tuning values for deterministic drift detection
- added unit and integration coverage for the new scheduler policy fields
