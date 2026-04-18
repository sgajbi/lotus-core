# Timeseries Generator Service

## Purpose

`timeseries_generator_service` materializes position time-series foundations in `lotus-core` and
stages the follow-on portfolio aggregation work needed for portfolio-level time-series completion.

It is part of the core derived-state layer that sits after persistence and position/valuation
materialization, but before downstream analytics services consume canonical time-series inputs.

## What it handles

The current runtime centers on:

- position time-series materialization
- idempotent re-materialization when upstream position or valuation state changes
- staging `portfolio_aggregation_jobs` for portfolio-day rollup work

Portfolio aggregation dispatch and execution are delegated to the dedicated portfolio aggregation
runtime rather than being fully owned inside this service.

## Runtime role

For affected portfolio-day state, the service:

1. consumes position and valuation-driven change signals
2. computes or updates `position_timeseries`
3. stages the portfolio-day aggregation job required for portfolio-level rollup
4. preserves replay safety and ordering for restated or late-arriving upstream data

This means the service is not just a passive snapshot expander. It is part of the governed pipeline
that keeps portfolio-level series supportable after position-level change.

## Data it owns

Primary durable outputs include:

- `position_timeseries`
- staged `portfolio_aggregation_jobs`

It works alongside:

- `portfolio_timeseries`
  produced by the delegated aggregation runtime
- `daily_position_snapshots`
  upstream valuation-state input

## Why it matters

`lotus-core` owns canonical time-series inputs used by downstream performance, risk, gateway, and
reporting consumers.

If this service is stale or incorrect:

- downstream analytics-input products become incomplete
- support surfaces can show valuation completion without matching time-series readiness
- portfolio-level rollups can lag even when security-level materialization is up to date

## Boundary rules

- `position_calculator` and `valuation` produce upstream state changes
- `timeseries_generator_service` owns position time-series materialization
- portfolio aggregation execution is delegated to the aggregation runtime
- downstream performance and risk conclusions do not belong here

## Operational hints

Check this service when:

- holdings or valuation state looks correct but time-series inputs are stale
- support evidence shows aggregation jobs not being re-armed
- position-level coverage exists but portfolio-level coverage is lagging

Check beyond this service when:

- `position_timeseries` is already current and only portfolio-level rollup is missing
- the defect is in downstream analytics interpretation rather than core input readiness

## Related references

- [System Data Flow](System-Data-Flow)
- [Data Models](Data-Models)
- [Operations Runbook](Operations-Runbook)
- [RFC-0083 Eventing Supportability Target Model](../docs/architecture/RFC-0083-eventing-supportability-target-model.md)
