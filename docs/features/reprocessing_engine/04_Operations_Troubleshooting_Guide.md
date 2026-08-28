# Operations & Troubleshooting Guide: Reprocessing Engine

This guide provides operational instructions for monitoring and troubleshooting the reprocessing engine.

## 1. Observability & Monitoring

The health and progress of the reprocessing engine can be monitored via key Prometheus metrics and support/lineage APIs.

### Key Metrics to Watch

* **`reprocessing_active_keys_total` (Gauge):**
    * **What it is:** The total number of `(portfolio_id, security_id)` keys currently in the `REPROCESSING` state.
    * **What to watch for:** This number should ideally be low or zero. A value that is persistently high or constantly growing indicates a systemic issue, such as a failing consumer or a "thundering herd" of back-dated events.

* **`scheduler_gap_days` (Histogram):**
    * **What it is:** Measures the gap in days between a key's `watermark_date` and the current business date when the `ValuationScheduler` runs.
    * **What to watch for:** Large gaps indicate that the valuation backfill process is lagging. This could be due to a slow consumer or an overwhelming number of jobs.

* **`epoch_mismatch_dropped_total` (Counter):**
    * **What it is:** A counter that increments every time a consumer discards a Kafka message because its epoch is stale.
    * **What to watch for:** A consistently high rate of dropped messages can indicate a "split-brain" scenario or a misbehaving producer that is still publishing events with an old epoch.

### Oversized repository batches

Valuation and reprocessing repositories split normalized caller-sized work into statements of no
more than 1,000 rows and within the governed PostgreSQL bind budget. When one logical operation
requires multiple statements, it emits one structured `database_statement_batch` event containing
bounded `operation`, `status`, and `reason_code` values plus `item_count`, `chunk_count`, and
`max_rows_per_statement`.

Use repeated multi-statement events to distinguish legitimate high-cardinality fan-out from a
database parameter failure. Do not treat multiple statements as partial commits: all chunks remain
inside the caller-owned transaction, and a later failure rolls back the logical operation. The
event deliberately omits portfolio, security, job, claim, and correlation identifiers; use support
and lineage APIs for drill-down.

## 2. API-First Monitoring

Use the API-first operational runbook:

`docs/operations/API-First-Operational-Playbook.md`

Primary calls for reprocessing workflows:

1. `GET /support/portfolios/{portfolio_id}/overview`
2. `GET /lineage/portfolios/{portfolio_id}/keys?reprocessing_status=REPROCESSING`
3. `GET /lineage/portfolios/{portfolio_id}/securities/{security_id}`

## 3\. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) | Key Log Message(s) / Metric Alert | Diagnosis & Resolution |
| :--- | :--- | :--- | :--- |
| **Stuck Reprocessing** | Data for a specific position is not updating. | `reprocessing_active_keys_total` is \> 0 and lineage keys remain `REPROCESSING`. | **Cause:** A consumer in the pipeline is failing, or the `position-calculator` crashed mid-replay. \<br\> **Resolution:** Check lineage key state via API, then inspect failing consumer logs. If the cause was transient, trigger reprocessing for the original back-dated transaction. |
| **Thundering Herd** | `scheduler_gap_days` is high and growing. `reprocessing_active_keys_total` is very high. | `Effective-dated price requires durable reprocessing.` appears frequently in `valuation_orchestrator_service` logs — `PriceEventConsumer` runs there, not in the calculator. | **Cause:** A back-dated price was ingested for a widely-held security, triggering a massive number of watermark resets. The system is struggling to keep up. \<br\> **Resolution:** This is a scalability challenge. The system will eventually catch up, but may require scaling up the consumer instances for the calculator services. |
| **Stale Data on API** | A user reports seeing old data for a position. | `epoch_mismatch_dropped_total` is increasing for the affected key. | **Cause:** The `position_state` has moved to a new epoch, but a producer is still emitting messages with the old epoch. \<br\> **Resolution:** Identify the misbehaving producer from the logs and restart it. The epoch fencing is working as designed by protecting the database, but the root cause must be fixed. |

```
```
