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

This makes the service more than a local calculation helper. It is the stage that turns canonical
transaction facts into governed cost-aware transaction state.

## Runtime role

For an eligible persisted transaction event, the service:

1. validates idempotency and portfolio readiness
2. loads the relevant transaction history for the portfolio-security key
3. normalizes the event into the cost engine's processing shape
4. enriches the timeline with portfolio policy and FX context where required
5. recalculates the applicable transaction sequence under the active cost-basis method
6. persists updated transaction cost fields, lot state, and related support records
7. publishes the enriched processed transaction event for downstream consumers

Because the service recalculates the governed transaction timeline rather than only patching the
latest row, it remains authoritative when late or out-of-order history is introduced.

## Data it owns

Primary durable outputs include:

- enriched transaction cost fields
- `transaction_costs`
- `position_lot_state`
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
