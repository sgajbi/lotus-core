# Cost Processing

## Purpose

The cost module is the transaction-enrichment and cost-basis authority inside the unified
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

PostgreSQL enforces the same ledger boundary: fee-component rows are positive, open lot quantity
and local/base basis are nonnegative, and open quantity cannot exceed original acquisition
quantity. Accrued-income signs remain methodology-owned because ex-coupon conventions require more
specific evidence than a generic nonnegative rule.

This makes the module more than a local calculation helper. It turns canonical transaction facts
into governed cost-aware state inside the same unit of work as cashflow and position processing.

## Runtime role

Pure models, ordering, lot disposition, FIFO/AVCO policy, corporate-action cash economics,
incremental and average-cost checkpoint state, and calculation diagnostics live in the
target-owned `app/domain/cost_basis` package behind one public domain API. The timeline
coordinator is target-owned application behavior behind a framework-neutral observation port;
Prometheus duration/depth recording, SQL persistence, and outbox staging are target infrastructure
adapters. `ProcessTransactionUseCase` remains the single combined application coordinator. The
repository explicitly maps the domain's `calculation_state_version` to the compatible
`engine_state_version` database column.

Deterministic AVCO rebuild planning is an application service under
`app/application/cost_basis_processing`. Upstream-provided cash-leg resolution and pairing is a
separate settlement service under `app/application/settlement_processing` over a narrow canonical
transaction lookup port. The same settlement package owns generated cash-leg validation,
construction, ordered persistence, and immutable product linkage through separate narrow lookup
and persistence ports. Cost-basis services operate on canonical booked transactions through
transaction-state, reference-data, and FX ports. The cost-basis application package owns the
persistence-scope decision for complete snapshots, selected FIFO lots, and atomic AVCO transitions.
The same package owns calculated transaction persistence: it writes the affected
timeline suffix through transaction, lot-state, and accrued-income-offset ports and returns
immutable booked transactions. Processed transactions and derived FX contract instruments cross a
typed effect-staging port as domain values. The transactional infrastructure adapter alone maps
those values to governed event DTOs, topics, payloads, lifecycle metrics, and outbox rows using the
same caller-owned SQL transaction.
SQLAlchemy-based AVCO reconciliation remains an infrastructure adapter under
`app/infrastructure/cost_basis`; it invokes the application planner and owns only persistence
coordination. Lot-opening, consumption, preservation, and basis-transfer behavior remains pure
policy under `app/domain/cost_basis`.

Timeline replay and bounded average-cost-pool reconciliation are grouped under the same cost-basis
capability in every layer. Their domain assessment, application use case, port, SQL adapter, and
tests use matching `cost_basis` or `cost_basis_processing` package paths; flat compatibility roots
are not extension points.

`PreparedCostProcessingUseCase` acquires the portfolio-security lock and delegates the
incremental-versus-full-rebuild decision to `CostBasisCalculationCoordinator`. It accepts an
immutable booked transaction, restores compatible FIFO lots or an AVCO pool through narrow ports,
enriches the calculation timeline with effective FX evidence, and invokes the governed timeline
processor. `coordinate_cost_processing_effects` then links settlement legs, reconciles corporate
actions, and stages domain-valued transaction and instrument effects. Framework event DTO mapping,
SQL transaction ownership, and outbox publication stay outside that application boundary behind
the cost-processing effect-staging port.

Cost-basis calculation observation remains framework-neutral at the port boundary. Prometheus
instruments and adapters are grouped under `app/infrastructure/cost_basis`; metric names, labels,
and buckets remain stable operational contracts. Transaction-persistence stages use the same typed
observation boundary, and the infrastructure adapter contains metric or logging failures so
telemetry cannot abort financial writes. Ordered-append/full-rebuild execution mode and restored-lot
counts also cross this typed boundary; calculation coordination does not import Prometheus objects.
Corporate-action basis-reconciliation metrics and support logs are separately named in
`app/infrastructure/cost_basis/corporate_action_observability.py` so this financial evidence remains
discoverable without returning a flat service-level telemetry module.

The legacy cost calculator source root, standalone consumer, mixed processor, and separate
physical-idempotency/retry/DLQ transaction boundary are retired and are not extension points. New
processing paths and tests use the combined application use case, target modules, and ports.

Ordinary transaction booking metadata and settlement-leg policy are owned by
`app/domain/transaction`, operate on immutable `BookedTransaction`, and are mapped back onto the
existing governed event envelope only in infrastructure. The shared transaction package no longer
contains duplicate BUY, SELL, DIVIDEND, or INTEREST canonical models or policy facades.

Foreign-exchange baseline economics, validation, and synthetic contract identity remain under
`app/domain/transaction/fx`. `app/application/foreign_exchange_processing` owns validated canonical
transaction persistence through a narrow port; infrastructure alone maps the resulting transaction
and optional contract instrument onto governed integration events.

For an eligible persisted transaction event, the service:

1. validates idempotency and portfolio readiness
2. acquires the transaction-scoped cost-basis lock for the normalized portfolio-security key
3. reads the versioned canonical cost-processing checkpoint for that key
4. normalizes the event into the cost-basis domain transaction model
5. uses durable open-lot state for a strictly ordered, compatible append, or loads full history for
   a backdated, same-order, unsupported, missing-checkpoint, or incompatible event
6. enriches the applicable rows with portfolio policy and FX context where required
7. calculates the ordered append or deterministic affected history under the active cost-basis method
8. persists the incoming row and any recalculated later suffix, plus lot, checkpoint, and support
   state, in one transaction through the cost-basis application persistence boundary
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
- unified cost processing owns processed transaction enrichment and lot-state authority
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
- [Position Processing](Position-Calculator)
- [Operations Runbook](Operations-Runbook)
- [Lotus Core Microservice Boundaries and Trigger Matrix](../docs/architecture/microservice-boundaries-and-trigger-matrix.md)
