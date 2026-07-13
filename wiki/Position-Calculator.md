# Position Processing

## Purpose

The position module maintains canonical position-history state inside the unified
`portfolio_transaction_processing_service` runtime.

It takes processed transaction events, recalculates the affected position path, and handles
reprocessing flows when late or back-dated activity would otherwise leave downstream state
inconsistent.

## What it handles

The current app-local/CI runtime centers on:

- accepting booked transactions through the unified application use case
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
5. stages supported compatibility effects needed by downstream materialization

When a transaction is back-dated, the runtime can trigger a broader reprocessing path instead of
pretending the new state can be patched in safely with a single forward update.

For mixed corporate actions, source-out and target-in security legs own security quantity and basis
movement. `CASH_CONSIDERATION` does not change security quantity or apply its disposed basis to the
remaining security position a second time. The linked `ADJUSTMENT` updates the cash instrument
position. Current security basis plus child security basis plus cash-disposed basis therefore
reconciles to original basis.

## Consolidated runtime

The app-local/CI unified transaction processor uses the same detection, ordering, lock, epoch
fence, and watermark rules, but rebuilds current-epoch position history inside the shared
transaction. This avoids depending on a legacy normal-path replay consumer. The combined path also
registers cost-stage pipeline readiness for every rebuilt current-epoch transaction before staging
matching cashflow completion signals. Legacy cost publication remains limited to the incoming
transaction so compatibility consumers cannot double-apply the rebuilt suffix. Compatibility events
remain for downstream stage orchestration while registry/Kubernetes cutover and remaining legacy
package removal are completed. The pure reducer and deterministic history builder live in
`app/domain/position`; the `PositionHistoryProcessor` application use case coordinates current and
backdated materialization through explicit ports; SQLAlchemy, state-store, and observability
adapters remain in infrastructure. The production unit of work passes immutable booked
transactions directly to this use case, avoiding the former event DTO round trip and duplicate
epoch-state read. The retired `position_calculator` source package is absent from the target image.

The former `position_calculation_workflow.py` and `position_repository.py` modules are no longer
production-composed. They remain temporarily as test-only compatibility code while their remaining
PostgreSQL concurrency/atomicity cases move to the canonical position package; issue `#719` tracks
deletion and an absence guard.

## Recalculation concurrency

Each destructive position-history delete/reinsert window holds a PostgreSQL advisory transaction
lock scoped to normalized portfolio, security, and epoch. A waiting calculation recomputes from
canonical transactions only after acquiring the lock, preventing a stale pre-lock result from
overwriting newer history. Different securities and epochs retain independent concurrency.

Backdated requests also use compare-and-set epoch advancement. One request advances the epoch; a
losing concurrent request is recorded as `coalesced/stale_epoch` and performs no replay or rebuild
work. After a winning rebuild commits, a later trigger whose transaction lineage is already present
in the current epoch is recorded as `coalesced/already_materialized`; it does not advance another
epoch or reread and rewrite history. The lookup uses the normalized
portfolio/security/epoch/transaction index and runs only for events already classified as
backdated.

Operators use the transaction-processing dashboard's position lock-wait p95, coordination rate,
and recalculation-work p95 panels with database pool and consumer-lag signals. The work histogram
distinguishes inline rebuild and coalesced zero-work decisions. Thresholds
require a deployed baseline.

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
- unified transaction processing owns canonical position-state transformation inside core
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
