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

## Runtime role

For an eligible portfolio-security-day valuation job, the service:

1. claims the next valuation job for processing
2. loads the required portfolio, instrument, price, and FX context
3. calculates valuation fields through shared valuation logic
4. upserts the daily snapshot record
5. updates valuation job status and supportability state

This is one of the key points where market/reference completeness directly affects downstream
readiness.

## Data it owns

Primary durable outputs include:

- `daily_position_snapshots`
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
- downstream performance and risk conclusions still belong outside `lotus-core`

## Operational hints

Check this service when:

- positions exist but `daily_position_snapshots` are stale or missing
- support evidence shows pending, failed, or repeatedly reset valuation jobs
- market data or FX completeness looks like the blocker to portfolio-day readiness

Check beyond this service when:

- valuation snapshots are current and only later time-series or downstream analytics surfaces are
  lagging
- the problem is shared ingress or non-core runtime governance

## Related references

- [System Data Flow](System-Data-Flow)
- [Timeseries Generator Service](Timeseries-Generator-Service)
- [Operations Runbook](Operations-Runbook)
- [Data Models](Data-Models)
- [RFC-0083 Market Reference Data Target Model](../docs/architecture/RFC-0083-market-reference-data-target-model.md)
