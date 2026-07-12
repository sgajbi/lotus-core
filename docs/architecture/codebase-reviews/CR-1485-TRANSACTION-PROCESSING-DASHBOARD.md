# CR-1485: Transaction Processing Dashboard

Date: 2026-07-10
Issue: #468
Status: Hardened locally; platform publication and alerts pending

## Objective

Provide one focused operational view for the combined cost, cashflow, and position runtime while
keeping the broad portfolio analytics dashboard aligned with the active scrape-job inventory.

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

The broad portfolio dashboard service filters now replace the retired cost, cashflow, and position
worker names with `portfolio_transaction_processing_service`. A repository test proves the unified
job remains visible and the three retired jobs cannot return to those filters.

## Threshold Decision

No alert thresholds are embedded yet. Local engine timings and unit tests do not establish a
production lag, latency, pool, or outbox SLO. Thresholds must be derived from deployed baseline and
failure-recovery evidence, then promoted to the canonical `lotus-platform` monitoring layer during
atomic cutover. This avoids false precision and alert noise.

## Compatibility

The focused dashboard is additive and app-local. The broad portfolio dashboard change follows the
already-completed app-local runtime cutover and changes no metric names, routes, public contracts,
or platform monitoring. It corrects operator visibility to match the active Prometheus job.

## Validation

- app-local observability contract pack: `5 passed`;
- exact dashboard UID and panel inventory proof;
- required live/replay/latency/failure/pool/outbox PromQL proof;
- business-identifier exclusion proof;
- unified-job presence and retired-job absence proof across the broad dashboard;
- Ruff lint/format and diff checks passed.

Platform dashboard publication and evidence-based alerts remain cutover prerequisites.
