# Data Models

## Purpose

`lotus-core` owns the canonical operational data model for foundational portfolio and transaction
state.

This page is an orientation map, not a schema dump. For exact fields and indexes, use:

- [database_models.py](https://github.com/sgajbi/lotus-core/blob/main/src/libs/portfolio-common/portfolio_common/database_models.py)
- [RFC-0083 Portfolio Reconstruction Target Model](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0083-portfolio-reconstruction-target-model.md)
- [RFC-0083 Ingestion Source Lineage Target Model](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0083-ingestion-source-lineage-target-model.md)
- [RFC-0083 Reconciliation Data Quality Target Model](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0083-reconciliation-data-quality-target-model.md)
- [RFC-0083 Source Data Product Catalog](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0083-source-data-product-catalog.md)
- [RFC-0083 Market Reference Data Target Model](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0083-market-reference-data-target-model.md)

## Current scope and reader map

This page describes the current `lotus-core` model ownership and supportability posture. It does
not certify that every additive target-model table is already active in every runtime consumer.
Where a staged migration is incomplete, the relevant model group states that boundary explicitly.

| Reader need | Start here |
| --- | --- |
| Portfolio, instrument, benchmark, and reference identity | Portfolio and reference masters |
| Booked activity, charges, and cash movement | Transactions and cashflows |
| Holdings, lots, pricing authority, and valuation state | Position and valuation state |
| Source lineage, replay, reconciliation, and operating evidence | Operational and control models |
| Exact columns, types, constraints, and indexes | `database_models.py` and the database schema catalog |

## Core model groups

### Portfolio and reference masters

Primary master and reference tables include:

- `portfolios`
- `instruments`
- `portfolio_benchmark_assignments`
- `benchmark_definitions`
- `index_definitions`
- `classification_taxonomy`
- `cash_account_masters`
- `instrument_lookthrough_components`

These tables define the static or slowly changing portfolio and instrument context consumed by
downstream operational and analytics-input contracts.

Every `portfolios` row requires a normalized, non-blank `tenant_id`. `legal_book_id` remains an
optional and independent business dimension; tenant, booking centre, and jurisdiction are not
legal-book substitutes. Portfolio ingestion cannot move an existing global `portfolio_id` to a
different tenant. The migration to this invariant stops with bounded diagnostic evidence when any
legacy row cannot be attributed, rather than fabricating ownership. Cross-tenant composite portfolio
identity and the remaining tenant-owned tables are later staged slices of issue `#798`.

`cash_account_masters` is the governed cash-account identity source for cash-balance account rows.
Transaction settlement cash-account strings can support fallback mapping only after they validate
against active/effective cash-account master rows for the same portfolio and cash instrument.
Raw transaction persistence may land unresolved settlement cash-account references only as
provisional source-batch ordering evidence; downstream lifecycle processing and source-data
products must block or degrade those rows until governed cash-account master data exists.

`instruments` is the governed instrument identity source for product transaction cost processing and
new BUY lot-state writes. Product transactions whose instrument master has not arrived are
retryable reference-data dependencies, not normal cost or lot-state writes. Raw transaction
persistence may land unresolved instrument references only as provisional source-batch ordering
evidence; downstream lifecycle processing and source-data products must block or degrade those rows
until governed instrument master data exists.

### Transactions and cashflows

Primary transaction-flow tables include:

- `transactions`
- `transaction_costs`
- `cashflows`

This layer is the canonical transaction ledger and normalized cash movement foundation. Downstream
services should not recreate these semantics independently.

`transaction_costs` is keyed at the normalized component grain
`(transaction_id, lower(trim(fee_type)), upper(trim(currency)))`. That grain prevents accidental
duplicate booked-fee evidence from inflating source-data products such as
`TransactionCostCurve:v1` and `PerformanceComponentEconomics:v1`.

The QCP transaction-economics adapter reads these tables with bounded keyset queries and maps ORM
rows into frozen booked-transaction, linked-cashflow, and cost-component evidence before application
policy executes. API/application code must not consume SQLAlchemy models directly.

### Position and valuation state

Primary position and valuation tables include:

- `position_history`
- `position_lot_state`
- `lot_amortized_cost_authority`
- `lot_amortized_cost_profiles`
- `lot_amortized_cost_periods`
- `accrued_income_offset_state`
- `daily_position_snapshots`
- `position_state`
- `instrument_valuation_policy_assignments`
- `market_price_source_facts`
- `daily_position_valuation_receipts`

This layer carries the reconstruction and valuation state needed to explain holdings as of a given
business date. Valuation-policy assignment rows preserve exact tenant, legal-book, instrument,
policy/version, effective-window, lifecycle, source revision, observation time, and rationale
history. The assignment store is append-only and source-version governed: exact replay is a no-op,
stale or divergent same-version content is rejected, and accepted versions are never updated in
place. Semantic corrections expose old/new authority and their earliest affected date for a later
bounded replay workflow; metadata-only corrections do not create valuation work. Runtime
correction-triggered replay remains separately governed.

Fixed-income book-cost source authority and profile history are staged separately from original/tax
lot basis. `lot_amortized_cost_authority` retains append-only policy-assignment, clean-cost,
contractual-schedule, and effective-yield source versions at exact source-lot scope. Its writer
serializes each upstream source stream, treats exact retries as unchanged, rejects divergent or
late lower versions, and its loader reconstructs typed domain facts with immutable-hash proof.
`lot_amortized_cost_profiles` is append-only at exact tenant, legal-book, portfolio, security, and
source-lot scope; it preserves active/parked lifecycle, source authority, calculation lineage, and
content hashes. Composite portfolio-book and source-lot foreign keys reject mixed-scope ledger
rows. `lot_amortized_cost_periods` preserves the ordered recognition schedule and each
period's input/output evidence. The repository serializes profile streams, requires contiguous
versions, treats an exact retry as unchanged, and fails closed on altered persisted evidence.
An application materializer reloads source authority only after acquiring the profile lock, appends
active profiles only when complete authority resolves, and persists a parked reason when it does
not. Corrections materialize the first inactive day after both prior and current inclusive
`valid_to` boundaries. A durable non-active decision explicitly unwinds accounting carry and
restores original-cost disposal economics; a missing profile remains fail closed.
`position_lot_state.lot_cost_local` and `lot_cost_base` remain strategy/tax acquisition basis.
Optional `amortized_book_carrying_local` and `amortized_book_carrying_base` fields separately retain
accounting carry with complete profile, recognition-boundary, schedule, FX, and calculation-lineage
evidence. The transaction runtime applies amortized carrying cost to disposal economics and uses a
durable source-lot-keyed correction command to replay the earliest affected booked transaction.
Canonical checkpoint fencing rebuilds the complete affected suffix, and the stable command id
suppresses duplicate financial work across Kafka redelivery. These internal structures still do
not make the complete fixed-income lifecycle or redemption a supported capability until protected
runtime, query, recovery/load, and downstream certification finish.

Financial `NUMERIC` persistence has an explicit finite-value policy. The machine-readable inventory
in `docs/standards/financial-numeric-persistence.v1.json` classifies all 146 ORM numeric columns
across 37 tables by nullability and signed, positive, or nonnegative semantics; every entry is
enforced. Source facts, client policy, position state, transaction economics, cashflows, derived
timeseries, and reconciliation reject PostgreSQL `NaN`, `Infinity`, and `-Infinity`. Sign checks
remain independent so legitimate signed cashflow, return, cost, market-value, and P&L fields are
not narrowed accidentally. Migrations add checks as `NOT VALID` before validating retained rows,
causing deployment to fail closed if historical contamination exists rather than coercing
financial evidence. Precision and scale remain separately governed under issue #829. Every
governed ORM column now uses a DDL-compatible exact-bind type: bounded values that PostgreSQL would
round or overflow are rejected before execution. The authoritative market-price source value and
the amortization period year-fraction/rate evidence remain exact-unbounded where truncation would
change source or calculation identity. Producer DTOs and calculated-output rounding policies remain
domain-owned; the persistence safety net does not authorize implicit or blanket rounding.

`market_price_source_facts` is an additive append-history authority store. Its source-version
identity is the stable upstream source system, source record, and positive correction version;
tenant, legal book, instrument, and price date are versioned authority payload and may move in a
later correction. Each row carries an explicit unit/clean-percent/dirty-percent quote basis,
governed lifecycle, normalized currency, source revision/content hash, and aware observation
evidence. A scope-history index finds candidate source identities, while the globally unique
source-version key supports latest-correction ranking before exact-scope and lifecycle selection.
Prices use exact unbounded PostgreSQL `NUMERIC`, matching the positive finite domain contract and
preventing silent scale rounding or magnitude overflow from turning an exact replay into a false
conflict.
The dedicated writer is insert-only, serializes source and old/new authority identities, treats an
exact replay as a no-op, and rejects divergent or competing authority. It does not replace or widen
the global `(security_id, price_date)` `market_prices` projection. The governed public write path is
`POST /ingest/authoritative-market-price-source-facts`; it uses the standard ingestion job and
idempotency lifecycle and maps correction/authority conflicts to a stable product-safe code. Both
write and read batches fail closed above 500 records and chunk SQL predicates at 100 keys; database
checks reject non-finite prices and observation times. Existing valuation,
reconciliation, query, freshness, demo, and replay consumers remain on that legacy projection until
both financial consumers complete a governed, tenant-safe cutover.

Scoped position-valuation jobs are the first staged consumer of this authority. They resolve the
exact policy assignment and market-price fact without reading the global projection, then persist a
one-to-one `daily_position_valuation_receipts` row alongside the snapshot and outbox event. A
supported receipt binds policy/assignment versions, immutable source references and hashes,
numeric-output policy, and deterministic input/calculation/output lineage. Unscoped compatibility
is explicitly marked unsupported and carries no invented authority evidence. Deterministic
authority failures replace the exact snapshot with failed/null derived state and remove stale
receipts in the same transaction. Financial reconciliation outer-joins the receipt in its
set-based snapshot read: supported unit-price evidence follows the recorded policy instead of the
legacy bond heuristic, while inconsistent authoritative evidence blocks. Principal-policy
reconciliation, correction-triggered replay, cross-event batching, Query exposure, and final
legacy deletion remain outside this staged cutover until #451 acceptance is complete.

### Timeseries and analytics-input foundations

Primary time-series tables include:

- `position_timeseries`
- `portfolio_timeseries`

These are upstream foundations for downstream analytics services. `lotus-core` owns the canonical
input products, not the downstream performance or risk conclusions built from them.
Failed or null-valued daily position snapshots are supportability state, not numeric zero: they do
trigger removal of current and immediate-successor position/portfolio timeseries plus aggregation
restaging while preserving later valued boundaries, and the timeseries calculation boundary
rejects null current or prior market values.

### Operations, lineage, and supportability

Primary operational tables include:

- `processed_events`
- `outbox_events`
- `portfolio_aggregation_jobs`
- `portfolio_valuation_jobs`
- `ingestion_jobs`
- `ingestion_job_failures`
- `ingestion_ops_control`
- `consumer_dlq_events`
- `consumer_dlq_replay_audit`
- `reprocessing_jobs`
- `analytics_export_jobs`
- `pipeline_stage_state`
- `financial_reconciliation_runs`
- `financial_reconciliation_findings`

These tables are part of the supported operational contract. Replay, support, lineage, and
reconciliation behavior is not incidental implementation detail in `lotus-core`.

## Model rules that matter

1. New temporal semantics must follow
   [Temporal Vocabulary](https://github.com/sgajbi/lotus-core/blob/main/docs/standards/temporal-vocabulary.md).
2. New source-data or analytics-input products must align with
   [RFC-0083 Source Data Product Catalog](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0083-source-data-product-catalog.md).
3. New security, retention, or operator-surface changes must align with
   [RFC-0083 Security Tenancy Lifecycle Target Model](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0083-security-tenancy-lifecycle-target-model.md).
4. New event or replay supportability changes must align with
   [RFC-0083 Eventing Supportability Target Model](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0083-eventing-supportability-target-model.md).

## When to update this page

Update this page when:

- a new durable table family becomes part of normal engineering work
- a target-model RFC introduces a new governed model group
- the operational supportability or reconciliation model materially changes

Do not copy every field here. Keep this page focused on stable ownership and navigation.
