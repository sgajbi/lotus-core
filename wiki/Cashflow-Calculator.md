# Cashflow Calculator

## Purpose

The cashflow calculator materializes canonical cashflow records from processed transaction events in
`lotus-core`.

It converts transaction semantics into normalized inflow and outflow state that downstream
timeseries, reconciliation, and supportability surfaces can rely on.

## What it handles

The current runtime centers on:

- consuming cost-processed transaction events
- resolving cashflow rules by transaction type
- normalizing amount sign and classification semantics
- persisting durable cashflow rows
- emitting cashflow completion events for downstream orchestration

This makes the service a governed semantic transformation stage, not a simple amount copy.

## Runtime role

For an eligible processed transaction event, the service:

1. validates replay and idempotency posture
2. resolves the effective processing transaction type
3. loads the governed cashflow rule for that transaction type
4. calculates the normalized amount, timing, and flow classification
5. persists the resulting cashflow row and stages the completion event

The service also keeps operational rule lookup supportable through cache refresh and invalidation
behavior rather than requiring a restart for every rule update.

## Data it owns

Primary durable outputs include:

- persisted `Cashflow` rows
- `cashflows.calculated` completion events
- semantic event-processing evidence used to prevent duplicate cross-topic publication

These outputs feed:

- pipeline orchestration and downstream readiness
- position and portfolio timeseries materialization
- transaction-to-cashflow reconciliation controls
- support and replay investigations

## Why it matters

If cashflow calculation is wrong:

- portfolio and position flow semantics become misleading even when the transaction ledger is
  correct
- timeseries can look complete while carrying the wrong flow direction or timing
- reconciliation controls lose credibility because ledger-to-cashflow alignment is no longer
  dependable

That is why cashflow normalization is part of the core system-of-record contract.

## Boundary rules

- processed transaction events are upstream input
- cashflow rule governance remains part of `lotus-core`
- cashflow calculator owns normalized cashflow materialization inside core
- downstream performance and risk analytics may consume this state, but they do not redefine it

## Operational hints

Check this service when:

- transaction history exists but expected portfolio or position flows are missing
- flow direction looks reversed for transaction types such as fees, deposits, transfers, or
  interest events
- cashflow-rule changes are not reflected in runtime behavior
- reconciliation surfaces report transaction-to-cashflow drift

Check beyond this service when:

- cashflows are already correct and only timeseries, valuation, or downstream analytics are stale
- the issue is earlier ingestion or persistence acceptance rather than cashflow semantics

## Related references

- [System Data Flow](System-Data-Flow)
- [Outbox Events](Outbox-Events)
- [Timeseries Generator Service](Timeseries-Generator-Service)
- [Operations Runbook](Operations-Runbook)
