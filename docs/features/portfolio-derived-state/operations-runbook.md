# Portfolio Derived-State Operations Runbook

This guide covers the position and portfolio materialization modules supervised by
`portfolio_derived_state_service`.

## 1. Observability & Monitoring

The health of this service is critical for the availability of all performance and risk analytics.

### Key Metrics to Watch

* **Consumer Lag:** Monitor `valuation.snapshot.persisted` lag for the preserved
  `timeseries_generator_group_positions` group.
* **Durable Queue:** Monitor pending, processing, failed, and expired
  `portfolio_aggregation_jobs`, oldest eligible age, claim throughput, and stale-claim recovery.
* **Queue outcomes:** `control_queue_operations_total{queue="aggregation"}` counts bounded claim,
  lease-recovery, complete, requeue, lost-ownership, terminal-failure, and execution-error outcomes.
  Alert on sustained `lost_ownership`, `failed`, or `execution_error` rates rather than parsing logs.
* **`events_dlqd_total` (Counter):** An increase means the delivery was malformed or the application could not durably record its failure. Missing governed source data normally leaves the aggregation job in `FAILED` for support-led remediation rather than duplicating failure evidence in the DLQ.
* **Materialization latency:** Attribute position-event handling and portfolio-job execution
  separately. Rising portfolio latency can indicate large fan-in, missing completeness, FX lookup
  pressure, or database contention.
* **Workload resources:** Governed bank-day profiles sample PostgreSQL connection use,
  idle-in-transaction connections, lock waiters, blocked sessions, and the exact combined
  container's CPU/memory. A completed governed run without a successful resource sample fails its
  evidence contract; sampling diagnostics expose bounded error types only.
* **FX correction replay:** Monitor `RESET_FX_WATERMARKS` through
  `/support/portfolios/{portfolio_id}/reprocessing-jobs`, including direct pair, earliest impacted
  date, status, age, correlation, and affected-position count. One pending row is coalesced per
  direct pair; repeated observations must not create an unbounded queue. A pair with no affected
  positions retries visibility only to the configured attempt limit and then completes as an
  observable successful no-op.
* **Business-date scope:** Valuation backfill and watermark contiguity use only seeded `GLOBAL`
  business dates. Calendar-day fallback is a recovery behavior used only when that governed
  calendar is entirely empty; weekend or holiday valuation rows are not normal output.
* **Source freshness:** A newer authoritative valuation snapshot refreshes the corresponding
  position-timeseries row and rearms portfolio aggregation even when instrument-local values are
  unchanged by a portfolio-base FX correction. Replaying an already materialized snapshot is a
  no-op.

## 2. Structured Logging & Tracing

All logs are structured JSON and are tagged with the `correlation_id`. Key log messages can help diagnose issues:

* **`"Position-timeseries materialization completed."`**: Confirms the position-timeseries application use case finished and reports whether current or dependent days changed.
* **`"Scheduler claimed ... jobs for processing"`**: Confirms the in-process scheduler is leasing
  durable portfolio-date work.
* **`"Found and claimed ... eligible aggregation jobs"`**: Confirms deterministic queue claims.
* **`"Missing FX rate from..."`**: A critical source-data error that causes the owned aggregation job to fail without publishing partial output.
* **`"Portfolio aggregation requires instrument reference data."`**: A position could not be tied to authoritative instrument metadata, so Core rejected the incomplete portfolio aggregate and failed the owned job.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) in API / Logs | Key Log Message(s) / Support API | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Incorrect Performance/Risk Figures** | TWR or Risk metrics exposed through the query stack are incorrect (e.g., unexpectedly low market value). | Compare `query_control_plane_service` support APIs such as `/support/portfolios/{portfolio_id}/overview` and `/support/portfolios/{portfolio_id}/aggregation-jobs` against logs. | **Cause:** The portfolio aggregation job may have run on incomplete inputs for a business date. <br> **Resolution:** Use control-plane support APIs to identify pending/failed jobs and replay path, then escalate with correlation IDs and support payloads. |
| **Analytics Data is Stale** | Performance and risk data is not available for the latest business date. | `GET /support/portfolios/{portfolio_id}/aggregation-jobs?status=PROCESSING` or `status=PENDING` returns growing backlog from `query_control_plane_service`. | **Cause:** Scheduler eligibility or upstream data completeness is blocking claims. <br> **Resolution:** Inspect position-timeseries worker and portfolio-aggregation scheduler logs for the affected portfolio and validate lineage progression via control-plane support APIs. |
| **Aggregation Jobs are Failing** | The support API reports `FAILED` aggregation jobs; DLQ growth occurs only when delivery validation or failure persistence also fails. | `FxRateNotFoundError`, `InstrumentReferenceNotFoundError`, or `Portfolio-timeseries materialization failed; marking the owned job failed.` | **Cause:** Required FX or instrument reference data is absent/invalid, or another calculation dependency failed. Core does not publish a partial portfolio aggregate. <br> **Resolution:** Correct the governed reference data, confirm position-timeseries completeness, and replay through the supported remediation path with the original correlation evidence. |
| **FX correction is not draining** | Corrected rate is durable but affected valuations remain stale or `RESET_FX_WATERMARKS` remains pending/processing. | Inspect pair/date lineage and affected-position count in the reprocessing-job support response, plus valuation and aggregation queue status. | **Cause:** Source event delivery, readiness visibility, replay ownership, or a downstream fail-closed market-data dependency blocked rematerialization. <br> **Resolution:** Preserve the source content hash/correlation ID, correct the blocking source data, and use the governed replay path. Do not schedule a global portfolio scan or substitute an inverse/triangulated pair. |

## 4. Gaps and Design Considerations

The exact-source fan-in profile is certified locally: 1,000 transactions produced exactly 1,000
snapshots, 1,000 position rows, and one portfolio row with clean reconciliation, closed queues,
zero lock waiters, and zero blocked sessions. Its portfolio-stage maximum was `1.723829s` against a
`900s` aggregation lease. This does not certify daily, price/FX burst, backdated, release, or
rollback behavior, and it does not yet close the fixed-lease versus heartbeat decision.

Daily, market-price burst/restatement, release, and rollback certification remains required before
#714 closure. Runtime consolidation does not permit position and portfolio workload metrics to lose
their separate attribution. FX correction is not covered by the market-price profiles. Core now
owns a versioned persisted FX event and bounded direct-pair replay. Certifying run
`20260715T233241Z` passed the five-business-date FX profile with exact corrected rows and values,
restart recovery, closed queues, clean reconciliation, and complete resource evidence; #791 is
locally fixed pending PR, CI, exact-main validation, and QA closure.

Run `make profile-derived-state-daily`, `make profile-derived-state-fan-in`,
`make profile-derived-state-price-burst`, `make profile-derived-state-price-restatement`, and
`make profile-derived-state-fx-restatement` for the managed certifying shapes. Correction profiles
require exact post-correction timestamps and values across all affected derived stages; the FX
profile additionally proves exact unrealized price, FX, and total P&L decomposition plus one
source observation and one direct-pair replay. It pauses valuation orchestration during correction
ingestion and requires complete recovery after restart.
`make test-derived-state-workload-smoke` is explicitly diagnostic and must not be
used as daily-volume, fan-in, lease-duration, or production-capacity evidence. Treat only a report
with `evidence_classification=certifying`, exact expected row counts, complete resource samples,
clean reconciliation, and no failures as profile evidence.
