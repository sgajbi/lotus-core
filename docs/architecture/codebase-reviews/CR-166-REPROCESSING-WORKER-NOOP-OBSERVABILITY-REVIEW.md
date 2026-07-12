## CR-166: Reprocessing worker no-op outcome observability

### Finding

`RESET_WATERMARKS` jobs that found no impacted portfolios were treated as successful completions, but that outcome was only visible in logs. Operationally, that is a distinct control result from a real watermark fanout.

Without a metric, operators could not tell the difference between:
- replay jobs that completed with real state mutation
- replay jobs that completed because there was nothing to mutate

### Fix

Added `reprocessing_worker_jobs_noop_total{job_type, reason}` to the shared monitoring layer and emitted it from the `no_impacted_portfolios` branch of `ReprocessingWorker`.

Also added unit proof that:
- no-op jobs do not mutate watermark state
- the no-op metric is emitted
- the durable job still completes cleanly

### Why this matters

This makes replay-control behavior observable in a more truthful way. In a banking system, a no-op control outcome is not a failure, but it is also not the same as a successful state mutation.

### Follow-up

If operators want this surfaced more prominently, add the new no-op counter to the replay section of the Grafana dashboard rather than treating it as log-only evidence.
