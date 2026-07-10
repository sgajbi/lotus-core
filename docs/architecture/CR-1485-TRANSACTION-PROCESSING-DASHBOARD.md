# CR-1485: Transaction Processing Dashboard

Date: 2026-07-10
Issue: #468
Status: Hardened locally; platform publication and alerts pending

## Objective

Provide one focused operational view for the combined cost, cashflow, and position runtime without
mixing cutover signals into the broad portfolio analytics dashboard.

## Change

Added the provisioned app-local dashboard
`grafana/dashboards/transaction_processing.json` with six bounded panels:

1. live consumer partition lag;
2. replay consumer partition lag;
3. transaction-processing stage p95 duration;
4. failed/rejected stage outcome rate;
5. async database pool state;
6. outbox pending count and oldest-pending age.

The dashboard uses the final live/replay group IDs and the governed shared/service-local metrics. It
contains no portfolio, transaction, correlation, trace, client, account, or security identifiers.

## Threshold Decision

No alert thresholds are embedded yet. Local engine timings and unit tests do not establish a
production lag, latency, pool, or outbox SLO. Thresholds must be derived from deployed baseline and
failure-recovery evidence, then promoted to the canonical `lotus-platform` monitoring layer during
atomic cutover. This avoids false precision and alert noise.

## Compatibility

The dashboard is additive and app-local. It does not add the undeployed target to Prometheus scrape
jobs, Compose, Kubernetes, or platform monitoring. Existing dashboards and runtime topology are
unchanged.

## Validation

- app-local observability contract pack: `4 passed`;
- exact dashboard UID and panel inventory proof;
- required live/replay/latency/failure/pool/outbox PromQL proof;
- business-identifier exclusion proof;
- Ruff lint/format and diff checks passed.

Platform dashboard publication and evidence-based alerts remain cutover prerequisites.
