# Cashflow Calculator

## Purpose

The cashflow module materializes canonical cashflow records inside the combined
`portfolio_transaction_processing_service` runtime.

It converts transaction semantics into normalized inflow and outflow state that downstream
timeseries, reconciliation, and supportability surfaces can rely on.

## What it handles

The current app-local/CI runtime centers on:

- receiving the cost-enriched transaction inside `ProcessTransactionUseCase`
- resolving cashflow rules by transaction type
- normalizing amount sign and classification semantics
- persisting durable cashflow rows
- retaining `cashflows.calculated` as a compatibility fact after atomic processing

This makes the module a governed semantic transformation stage, not a simple amount copy.

## Runtime role

The active workflow is implemented by
`portfolio_transaction_processing_service.app.infrastructure.cashflow_staging_workflow` and its
cashflow calculation/repository adapters. The retired standalone calculator consumer is not part of
the source tree or runtime.

For an eligible booked transaction, the module:

1. validates replay and idempotency posture
2. resolves the effective processing transaction type
3. loads the governed cashflow rule for that transaction type
4. calculates the normalized amount, timing, and flow classification
5. persists the resulting cashflow row and stages the completion event

Every transaction emitted by the cost stage traverses this workflow. For `AUTO_GENERATE` booking,
that includes both the product transaction and its generated settlement cash leg. Both rows retain
position-flow classification because they belong to the same linked transaction group; the
settlement row is not a portfolio flow, which prevents cash-account movement from being counted as
external portfolio funding.

The service also keeps operational rule lookup supportable through cache refresh and invalidation
behavior rather than requiring a restart for every rule update. Rule writes, including upgrade and
downgrade migrations, advance `cashflow_rules.updated_at` so every worker observes the new rule-set
version before serving another fresh cache hit.

For mixed corporate actions, `CASH_CONSIDERATION` produces a positive position-level product flow
classified as `CORPORATE_ACTION_PROCEEDS`; it is not income-since-inception. The real cash-account
movement is the linked `ADJUSTMENT`. A linked settlement flow is persisted for cash-position
accounting but has both position-flow and portfolio-flow flags disabled, preventing the settlement
record from double counting the product economics.

`CASH_IN_LIEU` follows the same product-versus-cash separation but is not income. Its fractional
product leg is a position-level `TRANSFER`, normally carrying a negative synthetic flow. The linked
`ADJUSTMENT` is the positive cash settlement and is excluded from position/portfolio product-flow
analytics. Equal-and-opposite linked amounts must sum to zero in settlement currency. Income-since-
inception calculations must exclude cash-in-lieu because its economics are capital disposal.

## Data it owns

Primary durable outputs include:

- persisted `Cashflow` rows
- `cashflows.calculated` completion events
- semantic event-processing evidence used to prevent duplicate cross-topic publication

These outputs feed:

- position and portfolio timeseries materialization
- transaction-to-cashflow reconciliation controls
- support and replay investigations

No active in-repo consumer waits for `cashflows.calculated`. Pipeline readiness is driven by the
atomic `transactions.cost.processed` completion fact, so restoring a cashflow readiness consumer
would reintroduce redundant ordering and lag failure modes.

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
- combined transaction processing resolves position recovery epochs before cashflow staging; an
  inline backdated rebuild rematerializes the deduplicated cashflow timeline in the new epoch
- downstream performance and risk analytics may consume this state, but they do not redefine it
- `PortfolioCashflowProjection:v1` has an implementation-backed methodology for daily operational
  net cashflow and cumulative cashflow across a bounded one-year operational horizon; it does not
  claim liquidity ladder, funding recommendation, tax, performance, market-impact, or OMS execution
  methodology

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
- [Mesh Data Products](Mesh-Data-Products)
