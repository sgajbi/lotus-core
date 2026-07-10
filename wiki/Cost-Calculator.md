# Cost Calculator

## Purpose

The cost calculator is the transaction-enrichment and cost-basis authority inside `lotus-core`.

It takes persisted transaction events, applies the portfolio's governed cost-basis policy, and
emits enriched processed transactions that downstream stages can trust for position, cashflow, and
supportability workflows.

## What it handles

The current runtime centers on:

- consuming persisted transaction events
- selecting FIFO or AVCO according to portfolio policy
- recalculating transaction cost and realized P&L state
- maintaining lot and related cost-basis support state
- publishing `transactions.cost.processed` for downstream fan-out

Lot-state persistence carries one remaining-state value per source BUY: open quantity, local cost
basis, and portfolio-base cost basis. FIFO reflects actual lot consumption. AVCO allocates the
remaining pooled quantity and cost pro rata across source contributions with exact aggregate
reconciliation; AVCO source rows are supportability lineage, not disposal-order lot selection.

This makes the service more than a local calculation helper. It is the stage that turns canonical
transaction facts into governed cost-aware transaction state.

## Runtime role

For an eligible persisted transaction event, the service:

1. validates idempotency and portfolio readiness
2. reads the versioned canonical cost-processing checkpoint for the portfolio-security key
3. normalizes the event into the cost engine's processing shape
4. uses durable open-lot state for a strictly ordered, compatible append, or loads full history for
   a backdated, same-order, unsupported, missing-checkpoint, or incompatible event
5. enriches the applicable rows with portfolio policy and FX context where required
6. calculates the ordered append or deterministic affected history under the active cost-basis method
7. persists the incoming row and any recalculated later suffix, plus lot, checkpoint, and support state, in one
   transaction
8. publishes only the incoming enriched event so downstream position handling is not duplicated

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
lazy aggregate scales. Large open-source-lot restoration on state-dependent disposal remains a
measured hotspot and a cutover capacity item.

## Data it owns

Primary durable outputs include:

- enriched transaction cost fields
- `transaction_costs`
- `position_lot_state`
- `cost_basis_processing_state`
- `accrued_income_offset_state`
- `position_state`
- `transactions.cost.processed` completion events

These outputs feed:

- position calculation
- cashflow calculation
- replay and supportability flows
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
