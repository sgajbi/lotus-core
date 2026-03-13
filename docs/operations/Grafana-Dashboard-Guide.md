# Grafana Dashboard Guide

## Access

- Grafana base URL: `http://localhost:3300`
- Dashboard URL: `http://localhost:3300/d/portfolio-analytics-overview/lotus-core-operational-overview`
- Default admin credentials:
  - username: `admin`
  - password: `admin`
- Anonymous viewer access is enabled in local Docker by default.

## What This Dashboard Is For

`Lotus Core Operational Overview` is the primary live operations dashboard for the local `lotus-core` platform. It is designed to answer four questions quickly:

1. Is the platform healthy right now?
2. Is replay or recovery pressure building?
3. Is durable event transport backing up or failing?
4. Are valuation, reconciliation, and analytics workloads converging normally?

This dashboard is intentionally organized as an operator surface, not a raw metric dump.

## How To Use It

Recommended local settings:

- Time range: `Last 15 minutes`
- Refresh interval: `10s`
- Use `Last 1 hour` when diagnosing replay or valuation backlogs that may have normalized recently.

Recommended reading order:

1. `Executive Summary`
2. `Critical Signals`
3. `API and Service Health`
4. `Replay, Recovery, and Outbox`
5. `Valuation and Timeseries`
6. `Reconciliation and Analytics`

## Section Guide

### Executive Summary

Use this section first. It provides the current platform shape in six signals:

- `Healthy Services`: how many of the expected Prometheus jobs are currently up
- `API Request Rate`: current request throughput across active HTTP services
- `Pending Outbox`: number of durable outbox rows still waiting to publish
- `Oldest Outbox Age`: age of the oldest pending outbox row
- `Active Reprocessing Keys`: current replay workload footprint
- `Ingestion Backlog Age`: age of the oldest unprocessed ingestion item

### Critical Signals

Use this section as the operator watchlist.

- `Durable Outbox Failures`
  - Non-zero means there are terminally failed outbox rows stored in the database.
- `Replay Stale Skip Rate`
  - Elevated values mean stale work is still colliding with live epoch-fenced state.
- `Valuation Failure Rate`
  - Persistent non-zero values mean the valuation pipeline is not converging cleanly.
- `Blocking Reconciliation Outcomes`
  - Persistent non-zero values mean reconciliation is actively producing control-blocking outcomes.

### API and Service Health

Use this section to answer whether the platform is reachable and serving.

- `HTTP Request Rate by Service`: identifies hot or silent services
- `Service Availability by Job`: immediate scrape-level health for each service
- `Average DB Operation Latency`: repository/method-level DB pressure indicator

### Replay, Recovery, and Outbox

Use this section when ingestion, replay, or event publication looks unhealthy.

- `Replay Audit Outcomes`: replay results by recovery path and status
- `Replay Pressure`: duplicate pressure, stale-skip pressure, and replay failures
- `Outbox Backlog and Publish Pressure`: durable publication queue health
- `Reprocessing Worker Throughput and Backlog`: claim/completion/failure balance, explicit no-op replay outcomes, and backlog age
- `Control Queue Pressure`: pending rows, terminal failures, and oldest pending age across the valuation, aggregation, and replay control queues

### Valuation and Timeseries

Use this section for scheduler/worker convergence.

- `Valuation Scheduling and Worker Health`: job creation, failures, worker claims, stale resets
- `Outbox Publication by Topic`: transport distribution across workflow topics

### Reconciliation and Analytics

Use this section for control-plane completion.

- `Reconciliation Outcomes and Findings`: business-control outcomes and finding pressure
- `Analytics Export Outcomes`: export success/failure by dataset type
- `Analytics Export Latency and Payload Depth`: p95 job duration, result size, and page depth

## Operator Workflows

### Workflow: Platform Looks Down

1. Check `Healthy Services`.
2. Check `Service Availability by Job`.
3. If services are up but traffic is flat, inspect `HTTP Request Rate by Service`.

### Workflow: Replay or Reprocessing Looks Stuck

1. Check `Replay Stale Skip Rate`.
2. Check `Replay Pressure`.
3. Check `Reprocessing Worker Throughput and Backlog`.
4. If `noop RESET_WATERMARKS / no_impacted_portfolios` is elevated, validate that replay requests are targeting real impacted holdings instead of broad security-wide resets.
5. Check `Ingestion Backlog Age` and `Active Reprocessing Keys`.
6. Check `Control Queue Pressure` to see whether replay backlog, durable failures, or pending age are isolated to replay or also spilling into valuation and aggregation queues.

### Workflow: Durable Events Are Not Moving

1. Check `Pending Outbox`.
2. Check `Oldest Outbox Age`.
3. Check `Durable Outbox Failures`.
4. Check `Outbox Backlog and Publish Pressure`.
5. Check `Outbox Publication by Topic` to identify the starving topic.

### Workflow: Valuation Is Not Converging

1. Check `Valuation Failure Rate`.
2. Check `Valuation Scheduling and Worker Health`.
3. Correlate with `Replay Stale Skip Rate` and `Reprocessing Worker Throughput and Backlog`.

### Workflow: Controls Are Blocking Portfolio-Day Completion

1. Check `Blocking Reconciliation Outcomes`.
2. Check `Reconciliation Outcomes and Findings`.
3. Correlate with replay and outbox pressure if reconciliation started failing after backlog growth.

## Data Source Assumptions

This dashboard expects:

- Grafana on `localhost:3300`
- Prometheus configured with the `Prometheus` datasource UID
- `lotus-core` Docker services exposing metrics and being scraped by Prometheus

## Related Files

- Dashboard JSON:
  - [portfolio_analytics.json](C:/Users/Sandeep/projects/lotus-core/grafana/dashboards/portfolio_analytics.json)
- Dashboard provisioning:
  - [dashboard.yml](C:/Users/Sandeep/projects/lotus-core/grafana/provisioning/dashboards/dashboard.yml)
- Docker topology:
  - [docker-compose.yml](C:/Users/Sandeep/projects/lotus-core/docker-compose.yml)
