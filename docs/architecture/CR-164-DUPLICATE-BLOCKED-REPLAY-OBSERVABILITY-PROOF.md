## CR-164: Duplicate-blocked replay observability proof

### Finding

`duplicate_blocked` replay outcomes were already surfaced through the ingestion recovery APIs, alert rules, and Grafana panels, and the shared monitoring layer already defined `ingestion_replay_duplicate_blocked_total`. The remaining weakness was proof: there was no lower-level test that `IngestionJobService.record_consumer_dlq_replay_audit(...)` actually incremented the duplicate-blocked metric on the real service path.

That left a gap between what operators were shown and what the codebase explicitly verified.

### Fix

Added direct unit proofs in `tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py` that:

1. `duplicate_blocked` replay audits increment:
   - `INGESTION_REPLAY_AUDIT_TOTAL{recovery_path, replay_status}`
   - `INGESTION_REPLAY_DUPLICATE_BLOCKED_TOTAL{recovery_path}`
2. `failed` replay audits increment:
   - `INGESTION_REPLAY_AUDIT_TOTAL{recovery_path, replay_status}`
   - `INGESTION_REPLAY_FAILURE_TOTAL{recovery_path, replay_status}`
3. the duplicate-blocked and failure counters do not cross-increment on the wrong status path.

### Why this matters

This is not cosmetic coverage. It locks the operator-facing replay pressure signal to the actual banking control path instead of assuming the metric stays wired correctly.

### Follow-up

If replay observability expands further, keep the metric proof at the service boundary and do not rely only on dashboard or alert configuration as evidence.
