# Position Calculator

## Purpose

The position calculator maintains canonical position-history state in `lotus-core`.

It takes processed transaction events, recalculates the affected position path, and handles
reprocessing flows when late or back-dated activity would otherwise leave downstream state
inconsistent.

## What it handles

The current runtime centers on:

- consuming processed transaction events
- recalculating next position state
- updating durable position-history state
- triggering atomic reprocessing flows for back-dated changes
- preserving replay safety through epoch and watermark controls

This makes the service more than a simple running-balance updater.

## Runtime role

For a processed transaction event, the service:

1. loads current position and reprocessing state
2. determines whether the transaction can be applied incrementally or requires reprocessing
3. calculates the next position state and related deltas
4. persists updated position history and state
5. emits or stages the downstream effects needed for valuation and later materialization

When a transaction is back-dated, the runtime can trigger a broader reprocessing path instead of
pretending the new state can be patched in safely with a single forward update.

## Data it owns

Primary durable outputs include:

- position-history state
- lot and state transitions that reflect the latest accepted transaction ledger
- reprocessing state used to keep replay and downstream recalculation coherent

These outputs feed:

- valuation jobs and daily snapshots
- time-series materialization
- support and reprocessing surfaces

## Why it matters

If position calculation is wrong:

- holdings truth becomes unreliable even when transactions were persisted correctly
- valuation and time-series readiness can look current while resting on incorrect state
- reprocessing of late activity becomes unsafe or operationally expensive

That is why position-calculation correctness and reprocessing posture are part of the core
system-of-record contract.

## Boundary rules

- processed transaction history is upstream input
- position calculator owns canonical position-state transformation inside core
- valuation and time-series materialization are downstream consumers of this state
- downstream analytics conclusions still belong outside `lotus-core`

## Operational hints

Check this service when:

- transaction history looks correct but holdings state is inconsistent
- back-dated transactions create supportability or replay anomalies
- downstream valuation lag follows an upstream position-state change
- reprocessing keys, jobs, or epoch-driven resets look stuck or noisy

Check beyond this service when:

- position state is already correct and only valuation or time-series layers are lagging
- the issue is ingestion acceptance rather than canonical state transformation

## Related references

- [System Data Flow](System-Data-Flow)
- [Valuation Calculator](Valuation-Calculator)
- [Operations Runbook](Operations-Runbook)
- [Data Models](Data-Models)
