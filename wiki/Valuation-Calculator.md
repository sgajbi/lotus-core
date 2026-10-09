# Valuation Calculator

## Purpose

The position valuation calculator materializes daily position valuation state in `lotus-core`.

It takes upstream holdings state, market/reference inputs, and valuation-job orchestration, then
produces governed `daily_position_snapshots` that feed downstream time-series and supportability
surfaces.

## What it handles

The current runtime centers on:

- claiming eligible `PortfolioValuationJob` work
- combining position history with market and FX inputs
- upserting `daily_position_snapshots`
- managing retry, stale-job reset, and superseded-job behavior

This makes the service a job-driven valuation worker, not a simple direct topic joiner.

## Current scope and evidence

The valuation worker, job repository, valuation domain logic, and valuation contract tests under
`src/services/calculators/` define the supported behavior. Market and FX completeness failures remain
visible as bounded or unavailable states; this page does not claim independent price authority.

## Reader Map

Authoritative price correction intents use the existing price consumer with a strict scoped
discriminator. For an admitted business date, it pages all held current-epoch positions within
the named tenant/book/security/date and stages valuation jobs plus the intent claim in one
transaction. A later-page failure rolls back every page. Completed jobs can be rearmed and
processing jobs request requeue through the existing job contract. The worker resolves current
persisted source authority; duplicate or delayed intents do not provide an old event price.
This bounded path does not certify future/calendar propagation, derived consumers, or latest
revision publication. QCP `READY` remains date coherence; overall current qualification still
requires reconciliation and data quality evidence.

| Reader need | Start with |
| --- | --- |
| Follow a valuation job | Runtime role |
| Diagnose missing inputs | Market, FX, and readiness sections |
| Verify supportability | Valuation contract tests and Operations Runbook |

## Runtime role

For an eligible portfolio-security-day valuation job, the service:

1. claims the next valuation job for processing
2. loads the required portfolio, instrument, price, and FX context
3. calculates valuation fields through shared valuation logic
4. upserts the daily snapshot record
5. updates valuation job status and supportability state

This is one of the key points where market/reference completeness directly affects downstream
readiness.

`ValuationJobProcessor` receives its database session provider and dependency factory explicitly.
Production `ValuationRepository`, idempotency, and outbox construction lives in
`app/infrastructure`; tests and alternate entry points inject that boundary rather than patching
processor globals. The processor remains transitional until persistence records, metrics,
publication, and transaction ownership are behind framework-neutral ports, so it must not be moved
into an `application` package based on its name alone.

## Data it owns

Primary durable outputs include:

- `daily_position_snapshots`
- one-to-one valuation receipts carrying supported authority evidence or explicit legacy-unscoped
  provenance; new non-flat legacy calculations include deterministic input, calculation,
  normalized-output, and numeric-output-policy lineage
- `PortfolioValuationJob` status transitions

These outputs feed:

- time-series materialization
- support and lineage surfaces
- reconciliation and readiness evidence

## Why it matters

If valuation is stale or incomplete:

- holdings can exist without current valued state
- time-series inputs can lag even when transactions and positions are already materialized
- downstream analytics-input products can look partially ready while still lacking usable market
  evidence

That makes valuation supportability a first-class contract, not just a calculation detail.

## Boundary rules

- position state is upstream input, not owned here
- market/reference and FX completeness materially affect this service
- valuation produces canonical daily snapshot truth inside core
- existing legacy receipts and flat quote-independent zero valuations may have null calculation
  lineage; absence remains explicit and is never backfilled by inference
- a non-flat bond requires exact effective-dated quote-policy and market-price source authority;
  unscoped bond prices fail closed because numeric magnitude cannot distinguish unit price from
  percent of principal
- runtime day-count authority must be exact and replayable; Core never infers a latest convention
  version
- downstream performance and risk conclusions still belong outside `lotus-core`

The framework-neutral domain kernel retains historical Lotus/SIFMA calendar-basis replay as
`30/360.US@1` and registers the explicit paired-February EOM policy as `30/360.US@2`. This domain
availability is not runtime product activation: no runtime, API, or database boundary selects or
persists version 2 in this slice. Issue #788 owns the supported source-term, persistence, API, and
consumer integration.

## Operational hints

### Database outage recovery

PostgreSQL connection-not-ready, connection refusal, and DNS resolution failures remain retryable
deliveries rather than terminal FAILED job writes. Authentication, permission, and financial
validation errors retain terminal handling. Recovery preserves the event and fenced claim; it does
not relax leases, retry budgets, or settlement limits.

Database health is not settlement evidence. Check the exact durable job, snapshot, processed-event
receipt, and staged outbox record. With default disabled retry budgets, broker redelivery requires
consumer restart or rebalance. Outbox staging is not publication, and controlled application
redelivery does not certify broker recovery. Follow the
[valuation database outage recovery runbook](https://github.com/sgajbi/lotus-core/blob/main/docs/operations/runbook.md#valuation-database-outage-recovery)
for the operational boundary and evidence to retain.

Check this service when:

- positions exist but `daily_position_snapshots` are stale or missing
- support evidence shows pending, failed, or repeatedly reset valuation jobs
- market data or FX completeness looks like the blocker to portfolio-day readiness
- a bond job reports `bond valuation requires explicit quote-convention authority`; assign the
  governed valuation policy and source representation for the exact tenant, legal book, security,
  and effective date rather than changing the price or cost basis to influence interpretation

Check beyond this service when:

- valuation snapshots are current and only later time-series or downstream analytics surfaces are
  lagging
- the problem is shared ingress or non-core runtime governance

## Related references

- [System Data Flow](System-Data-Flow)
- [Portfolio Derived State](Timeseries-and-Aggregation)
- [Operations Runbook](Operations-Runbook)
- [Data Models](Data-Models)
- [RFC-0083 Market Reference Data Target Model](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0083-market-reference-data-target-model.md)
