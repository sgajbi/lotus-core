# CR-084 Analytics Export Dashboard Review

## Scope
- `grafana/dashboards/portfolio_analytics.json`
- `src/libs/portfolio-common/portfolio_common/monitoring.py`

## Finding
The platform already exported analytics-export metrics for:

- job outcomes by dataset type and terminal status
- job duration
- result payload size
- page depth traversed during export assembly

None of those were visible in the bundled Grafana overview. Operators therefore had no dashboard-level signal for whether analytics export workloads were succeeding, slowing down, or producing unexpectedly large results.

## Change
Added two Grafana panels:

1. `Analytics Export Job Outcomes per Second`
2. `Analytics Export Depth and Latency`

The first panel exposes job-rate by `dataset_type` and `status`. The second exposes p95 duration, result size, and page depth by dataset type using the existing histogram metrics.

## Why this is the right fix
- no new instrumentation was required
- no runtime semantics changed
- the dashboard now covers another active control-plane workload
- this extends the same observability program established in CR-074 and CR-078 through CR-081

## Residual follow-up
- If analytics export operations become important enough operationally, move them into a dedicated control-plane dashboard instead of growing the overview forever.
- If p95 is not the most useful quantile operationally, revisit the panel expressions with real production feedback.

## Evidence
- `grafana/dashboards/portfolio_analytics.json`
- `src/libs/portfolio-common/portfolio_common/monitoring.py`
