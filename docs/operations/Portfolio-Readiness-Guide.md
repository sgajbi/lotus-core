# Portfolio Readiness Guide

## Purpose

`GET /support/portfolios/{portfolio_id}/readiness` is the source-owned readiness contract for one portfolio.

Use it when a UI, gateway, or downstream service needs to know whether holdings, pricing, transactions, and reporting are actually ready. Do not infer readiness from row counts, latest dates, or missing-response heuristics when this API is available.

## Why This Exists

Operational consumers previously had to guess readiness from indirect signals such as:

1. latest transaction date
2. latest position snapshot date
3. whether analytics rows happened to exist
4. whether reporting was blocked downstream

That approach was too weak for private-banking and wealth-management workflows. It hid real upstream blockers such as:

1. current-epoch snapshots lagging the booked ledger
2. unvalued positions still present on the latest booked snapshot date
3. active reprocessing backlog
4. cross-currency transactions that cannot be priced historically because historical FX prerequisites are missing

This API makes those blockers explicit.

## Endpoint

`GET /support/portfolios/{portfolio_id}/readiness`

Query parameters:

1. `as_of_date`
   Scope readiness to booked state on or before this date.
2. `stale_threshold_minutes`
   Threshold used to classify stale processing jobs.
3. `failed_window_hours`
   Time window used for recent failed-job support signals.

## Readiness Domains

The response is split into four domains:

1. `holdings`
   Current-epoch holdings and snapshot coverage.
2. `pricing`
   Valuation and historical-prerequisite readiness.
3. `transactions`
   Ledger and transaction-prerequisite readiness.
4. `reporting`
   Source-owned reporting and publication readiness.

Each domain returns:

1. `status`
   One of `READY`, `PENDING`, `BLOCKED`, `NO_ACTIVITY`.
2. `reasons`
   Explicit machine-readable reasons for the current state.

## Status Semantics

1. `READY`
   No known blocker or convergence reason remains for the domain.
2. `PENDING`
   Work is still converging or coverage is incomplete, but no terminal blocker is known.
3. `BLOCKED`
   A real source-owned blocker exists and downstream consumers should not treat the domain as ready.
4. `NO_ACTIVITY`
   No booked activity or snapshot state exists for the domain at the resolved as-of date.

## Historical FX Dependency Signals

`missing_historical_fx_dependencies` is intentionally first-class.

It reports cross-currency transactions that are missing historical FX prerequisites against the portfolio base currency. When present, this is not a cosmetic warning:

1. transactions are not fully ready
2. holdings and pricing may not be fully trustworthy
3. reporting should not infer readiness from downstream partial rows

Representative affected transactions are returned in `sample_records` to support operator triage and downstream diagnostics.

## Recommended Consumer Behavior

1. Use `reporting.status` for publish/report gating.
2. Use `pricing.status` before showing valuation-sensitive analytics.
3. Use `transactions.status` before presenting historical transaction-derived cash or FX summaries as complete.
4. Surface `blocking_reasons` directly in operator and support tooling instead of rewriting the logic downstream.
5. Treat `missing_historical_fx_dependencies.missing_count > 0` as a real upstream defect or data-ingestion gap, not as a UI-only warning.

## Design Boundary

This endpoint belongs in the query control plane because it is a curated, support-oriented integration contract.

It is not a raw canonical read API. It packages multiple upstream states into one explicit readiness contract for operators and downstream consumers.
