# Cost Calculator

## Purpose

The cost module is the transaction-enrichment and cost-basis authority inside the combined
`portfolio_transaction_processing_service` runtime.

It takes persisted transaction events, applies the portfolio's governed cost-basis policy, and
stages enriched processed transactions after cost, cashflow, and position effects have completed in
one atomic use case.

## What it handles

The current app-local/CI runtime centers on:

- consuming persisted transaction events
- selecting FIFO or AVCO according to portfolio policy
- recalculating transaction cost and realized P&L state
- maintaining lot and related cost-basis support state
- publishing `transactions.cost.processed` as the authoritative atomic completion fact

Lot-state persistence carries one remaining-state value per source BUY: open quantity, local cost
basis, and portfolio-base cost basis. FIFO reflects actual lot consumption. AVCO allocates the
remaining pooled quantity and cost pro rata across source contributions with exact aggregate
reconciliation; AVCO source rows are supportability lineage, not disposal-order lot selection.

This makes the module more than a local calculation helper. It turns canonical transaction facts
into governed cost-aware state inside the same unit of work as cashflow and position processing.

## Runtime role

The active application workflow is `app/cost_calculation_workflow.py`, imported directly by target
infrastructure. `app/consumer.py` is a quarantined compatibility shell for legacy delivery tests and
must not be imported by the combined runtime.

For an eligible persisted transaction event, the service:

1. validates idempotency and portfolio readiness
2. acquires the transaction-scoped cost-basis lock for the normalized portfolio-security key
3. reads the versioned canonical cost-processing checkpoint for that key
4. normalizes the event into the cost engine's processing shape
5. uses durable open-lot state for a strictly ordered, compatible append, or loads full history for
   a backdated, same-order, unsupported, missing-checkpoint, or incompatible event
6. enriches the applicable rows with portfolio policy and FX context where required
7. calculates the ordered append or deterministic affected history under the active cost-basis method
8. persists the incoming row and any recalculated later suffix, plus lot, checkpoint, and support state, in one
   transaction
9. publishes only the incoming enriched event so downstream position handling is not duplicated

The same key lock protects FIFO, AVCO, backdated rebuild, replay, first-write, and historical AVCO
repair paths. A waiting calculation reads canonical state only after the prior transaction commits,
so it cannot overwrite newer lot quantities with a stale in-memory result. Different securities
retain independent concurrency. `cost_basis_processing_lock_wait_seconds` and the `Cost Basis Lock
Wait p95` dashboard panel expose bounded contention without business identifiers in metric labels.

Because the service recalculates the governed transaction timeline rather than only patching the
latest row, it remains authoritative when late or out-of-order history is introduced. A timeline
engine error fails closed before suffix updates; operators should remediate the invalid historical
row rather than accepting a partially corrected cost history.

Cross-currency history is read once per normalized trade/base currency pair. Each read contains the
latest rate before the earliest requested date plus the bounded effective-date window, and each
transaction receives the latest rate on or before its booking date. Same-currency rows skip FX
access. A missing effective seed fails the attempt for retry; Core never substitutes a future or
default rate.

Developers can reproduce long-history engine scaling with:

```bash
make profile-cost-history-capacity
make profile-cost-processing-modes
```

The commands write `output/cost-history-capacity-profile.json` and
`output/cost-processing-mode-capacity-profile.json`. They characterize parser, sorter, FIFO/AVCO,
ordered lot opening, ordered disposal, and backdated rebuild engine cost; they do not certify
deployed throughput. FIFO availability checks are constant-time and AVCO source allocation uses
lazy aggregate scales. Ordered FIFO disposal streams only the oldest source lots needed to cover
the requested quantity and updates only that selected set. Ordered AVCO acquisition/disposal locks
and restores one versioned `average_cost_pool_state` source, then reconciles externally visible lot
lineage with set-based exact-residual SQL. Full rebuilds, basis transfers, and unsupported corporate
actions retain complete snapshots. Existing AVCO portfolios require governed historical backfill
before source evidence can be declared current after cutover.

Audit historical AVCO state before cutover with `make audit-average-cost-pools`. The command is
read-only by default, processes a bounded deterministic page, compares both persisted
representations with canonical replay truth, and returns a machine-readable resume cursor. After
review, use `make reconcile-average-cost-pools` with a portfolio scope and bounded limit. Each key
commits independently only after exact source-count, quantity, local-basis, and base-basis
certification. Retain output reports as release evidence; tool availability does not prove that a
historical estate has already been reconciled.

## Combined runtime replay controls

The app-local/CI combined transaction-processing runtime keeps operator replay as a second consumer
in the same deployable. Normal booking and replay load separate group-scoped execution profiles, so
replay throughput can be bounded without reducing live booking capacity. The shared loop preserves
Kafka partition order, permits only one active message per partition, reports ordered backlog
pressure, and commits only after replay publication succeeds. After commit,
`kafka_consumer_partition_lag_messages` reports cached high-watermark lag separately for live and
replay groups without adding a broker query to the transaction path.

The same target health surface samples `database_pool_connections` after successful database
readiness. Operators can correlate checked-out capacity and overflow with transaction latency,
consumer lag, and outbox age without adding persistence access to calculation code.

Use the app-local `Lotus Core Transaction Processing` dashboard to view those signals together.
Alert thresholds remain deliberately unset until deployed baseline and recovery measurements are
available; local engine timings are not production SLO evidence.

Shutdown is drain-first: polling stops, already-polled replay work completes and commits, and only
then are Kafka resources closed. Retry exhaustion, DLQ publication, and offset handling remain owned
by the shared consumer; the replay delivery mapper and application use case do not implement a
second transport loop.

The combined processing authority uses a versioned portfolio/transaction/epoch semantic key plus a
canonical SHA-256 booked-transaction fingerprint. Republishing identical content at another Kafka
offset returns `DUPLICATE` before cost, cashflow, position, or outbox work. Changed material content
under the same semantic key fails as `transaction_semantic_conflict`; correction and restatement
must use their governed lifecycle rather than masquerading as replay. Replay audit evidence remains
owned by the replay control boundary, not duplicate financial facts.

## Mixed corporate-action cash consideration

True cash consideration is processed as a basis disposal, not income. The product marker requires
source-owned allocated local and base basis. Same-currency processing derives realized capital P&L
as net proceeds less allocated basis and records zero FX P&L. Cross-currency processing requires an
explicit capital/FX split that reconciles to total P&L.

Bundle A reconciliation uses:

```text
source basis out = target basis in + cash-allocated basis
```

Missing cash basis fails closed and creates `insufficient_cash_basis` reconciliation evidence.

## Cash-in-lieu fractional disposal

`CASH_IN_LIEU` is a separate fractional product disposal, not income and not generic cash
consideration. It requires positive fractional quantity and proceeds plus source-owned allocated
local/base basis. The lot engine must consume exactly that quantity and basis. Same-currency P&L is
capital with zero FX; cross-currency capital and FX components are explicit and must reconcile to
total proceeds less basis.

The product leg carries the fractional basis and P&L. Its linked `ADJUSTMENT` carries the real cash
account movement and receives effective-dated FX plus signed local/base cash basis. Product and cash
flows are equal and opposite in settlement currency, so the linked flow sum is zero without
double-counting the economic disposal.

## Data it owns

Primary durable outputs include:

- enriched transaction cost fields
- `transaction_costs`
- `position_lot_state`
- `cost_basis_processing_state`
- `average_cost_pool_state`
- `accrued_income_offset_state`
- `position_state`
- `transactions.cost.processed` completion events

These outputs feed:

- pipeline readiness after the combined transaction commits
- replay and supportability flows through the combined runtime
- realized P&L and disposal traceability

## Why it matters

If cost calculation is wrong:

- realized P&L becomes unreliable
- position cost basis drifts even when transaction persistence is correct
- downstream cashflow and position stages can look operational while resting on the wrong enriched
  transaction semantics
- replay and audit investigations lose a key source of deterministic truth

That is why cost-basis policy and processed-transaction output belong to `lotus-core` as canonical
domain behavior, not as downstream interpretation.

## Boundary rules

- persisted transaction facts are upstream input
- portfolio-level cost-basis method selection is governed inside core
- cost calculator owns processed transaction enrichment and lot-state authority
- downstream analytics services may consume realized and cost-aware state, but they do not redefine
  it

## Operational hints

Check this service when:

- realized P&L or disposed cost basis looks wrong
- FIFO versus AVCO behavior does not match portfolio policy
- late transaction insertion causes downstream drift
- cross-currency processing shows unexpected FX query growth or missing-rate retries
- `cost_processing_execution_total` shows unexpected full-rebuild volume
- `cost_processing_open_lots_restored` shows growing disposal restore depth
- `transactions.cost.processed` lag or replay anomalies appear

Check beyond this service when:

- persisted source transactions are missing or malformed before they ever reach cost processing
- cost-aware transaction state is already correct and only later position, cashflow, or valuation
  stages are lagging

## Related references

- [System Data Flow](System-Data-Flow)
- [Cashflow Calculator](Cashflow-Calculator)
- [Position Calculator](Position-Calculator)
- [Operations Runbook](Operations-Runbook)
- [Lotus Core Microservice Boundaries and Trigger Matrix](../docs/architecture/microservice-boundaries-and-trigger-matrix.md)
