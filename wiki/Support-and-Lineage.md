# Support and Lineage

## Purpose

Support and lineage routes are the operator-facing evidence surface for runtime truth inside
`lotus-core`.

They let operators and downstream support tooling inspect whether a portfolio is healthy, blocked,
stale, replaying, unreconciled, or missing adjacent artifacts without inferring that state from raw
tables.

## What it handles

The current runtime centers on:

- support overview and source-owned readiness
- calculator SLO and queue-pressure summaries
- portfolio-day control-stage visibility
- reprocessing key and reprocessing job listings
- valuation, aggregation, and analytics export job listings
- reconciliation run and finding drill-through
- lineage-key discovery and portfolio-security lineage inspection

This makes the surface more than troubleshooting convenience. It is the governed operational
evidence plane for portfolio processing.

## Runtime role

The main routes are grouped around two concepts:

1. `support`
   portfolio-scoped operational state such as overview, readiness, SLOs, control stages,
   reprocessing, reconciliation, and durable job queues
2. `lineage`
   portfolio and portfolio-security lineage discovery for current epoch, watermark, and adjacent
   artifact truth

These routes are designed to answer questions like:

- is this portfolio blocked or simply stale?
- which durable control stage is driving the current status?
- are replay keys or replay jobs still active?
- do current epoch artifacts exist for positions, snapshots, and valuation jobs?
- which reconciliation run produced the current finding set?

## Why it matters

If support and lineage surfaces are weak:

- operators fall back to direct database inspection for routine triage
- downstream tooling can misclassify readiness or supportability from partial signals
- replay, reconciliation, and job-state investigation becomes slower and less auditable
- route consumers lose a common vocabulary for backlog, stale state, and blocking controls

That is why these routes are published as governed control-plane evidence instead of being treated
as internal-only diagnostics.

## Boundary rules

- these routes publish supportability and evidence, not front-office analytics
- readiness and support overview are not substitutes for portfolio timeseries or snapshot products
- lineage routes explain current durable artifact state; they do not replace replay or calculator
  ownership
- when the issue is shared ingress or cross-repo runtime wiring, move to `lotus-platform`

## Operational hints

Start with:

- `GET /support/portfolios/{portfolio_id}/overview`
- `GET /support/portfolios/{portfolio_id}/readiness`

Drill deeper with:

- `GET /support/portfolios/{portfolio_id}/control-stages`
- `GET /support/portfolios/{portfolio_id}/reprocessing-keys`
- `GET /support/portfolios/{portfolio_id}/reprocessing-jobs`
- `GET /support/portfolios/{portfolio_id}/reconciliation-runs`
- `GET /lineage/portfolios/{portfolio_id}/keys`

Use these routes before going directly to the database unless rollout mismatch or schema doubt makes
API evidence insufficient.

## Related references

- [Query Control Plane](Query-Control-Plane)
- [Event Replay Service](Event-Replay-Service)
- [Financial Reconciliation](Financial-Reconciliation)
- [Operations Runbook](Operations-Runbook)
- [Troubleshooting](Troubleshooting)
