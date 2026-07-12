# CR-081 Outbox and Valuation Dashboard Review

## Scope
- `grafana/dashboards/portfolio_analytics.json`
- `src/libs/portfolio-common/portfolio_common/monitoring.py`
- existing producers of outbox and valuation metrics

## Finding
The platform already exported useful reliability signals for:

- outbox backlog and publish failure/retry pressure
- valuation job creation, terminal failure, worker claim rate, and stale reset rate

Those metrics were not visible in the bundled Grafana overview. Operators therefore had no direct dashboard-level view into whether event publication was backing up or whether valuation scheduling and worker processing were healthy.

## Change
Added two Grafana panels:

1. `Outbox Backlog and Publish Pressure`
2. `Valuation Scheduling and Worker Health`

The outbox panel surfaces queue depth plus publish/retry/failure rate. The valuation panel surfaces job creation, terminal failure rate, worker claim rate, and stale reset rate.

## Why this is the right fix
- the metrics already existed and were stable
- no runtime semantics changed
- the dashboard now exposes another layer of operational truth without adding API complexity
- this complements CR-074, CR-078, CR-079, and CR-080

## Residual follow-up
- If the dashboard becomes too crowded, split reliability panels into a dedicated operational dashboard.
- If valuation operators need per-portfolio or per-security detail, expose that through targeted control-plane views rather than high-cardinality Prometheus labels.

## Evidence
- `grafana/dashboards/portfolio_analytics.json`
- `src/libs/portfolio-common/portfolio_common/monitoring.py`
