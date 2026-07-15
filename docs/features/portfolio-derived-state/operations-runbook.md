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

## 4. Gaps and Design Considerations

The exact-source fan-in profile is certified locally: 1,000 transactions produced exactly 1,000
snapshots, 1,000 position rows, and one portfolio row with clean reconciliation, closed queues,
zero lock waiters, and zero blocked sessions. Its portfolio-stage maximum was `1.723829s` against a
`900s` aggregation lease. This does not certify daily, price/FX burst, backdated, release, or
rollback behavior, and it does not yet close the fixed-lease versus heartbeat decision.

Daily, price/FX burst, backdated, release, and rollback certification remains required before #714
closure. Runtime consolidation does not permit position and portfolio workload metrics to lose
their separate attribution.

Run `make profile-derived-state-daily` and `make profile-derived-state-fan-in` for the two managed
certifying shapes. `make test-derived-state-workload-smoke` is explicitly diagnostic and must not be
used as daily-volume, fan-in, lease-duration, or production-capacity evidence. Treat only a report
with `evidence_classification=certifying`, exact expected row counts, complete resource samples,
clean reconciliation, and no failures as profile evidence.
