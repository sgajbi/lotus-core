# Cashflow Calculator

## Purpose

The cashflow module materializes canonical cashflow records inside the combined
`portfolio_transaction_processing_service` runtime.

It converts transaction semantics into normalized inflow and outflow state that downstream
timeseries, reconciliation, and supportability surfaces can rely on.

Current scope is cashflow materialization inside the combined transaction worker. This page does
not assign ownership of valuation, performance, risk, advice, or downstream liquidity decisions.

## Reader Map

| Need | Start with |
| --- | --- |
| Understand calculation ownership | Runtime role |
| Diagnose a missing or reversed flow | Operational hints |
| Verify durable outputs and events | Data it owns |
| Check transaction-family semantics | Runtime role and boundary rules |

## What it handles

The current app-local/CI runtime centers on:

- receiving the cost-enriched transaction inside `ProcessTransactionUseCase`
- resolving cashflow rules by transaction type
- normalizing amount sign and classification semantics
- persisting durable cashflow rows
- retaining `cashflows.calculated` as a compatibility fact after atomic processing

This makes the module a governed semantic transformation stage, not a simple amount copy.

## Runtime role

Canonical amount, sign, timing, level, transfer, income, fee, and corporate-action semantics live
in the framework-neutral
`portfolio_transaction_processing_service.app.domain.cashflow.calculation` policy. It consumes an
immutable `BookedTransaction` and returns an immutable `CalculatedCashflow`.

Application coordination lives in
`portfolio_transaction_processing_service.app.application.cashflow_processing`. Governed ports
separate rule resolution, processing state, persistence, event staging, and observability. Concrete
adapters are organized under `app.infrastructure.cashflow`; each composed runtime owns one
concurrency-safe rule cache and immutable source-versioned snapshots. Event DTO mapping, metrics,
logging, SQLAlchemy row construction, persistence, and outbox publication remain infrastructure
concerns. Framework events are mapped once to `BookedTransaction`; the domain result is mapped to a
database row only inside the repository adapter. The retired standalone calculator consumer,
compatibility workflow, and event-to-ORM calculation facade are not part of the source tree or
runtime.

Cash-entry mode validation, generated settlement-leg economics, and upstream product/cash pairing
are service-owned transaction-domain policies over immutable `BookedTransaction`. Framework event
DTOs remain at the infrastructure boundary and are not domain inputs.

INTEREST settlement uses a shared transaction-domain policy. `net_interest_amount` excludes
transaction fees: income cashflow subtracts the fee and expense cashflow adds it before applying the
cashflow sign. Explicit and derived pre-fee net amounts are therefore source-shape invariant. When
supporting a discrepancy, compare gross interest, withholding tax, other deductions, resolved fee
components, direction, and the linked cashflow amount; do not infer final settlement cash from
`net_interest_amount` alone.

The same settlement boundary governs ordinary BUY, SELL, and DIVIDEND cash. Component fee fields
override aggregate `trade_fee` when present. Current DIVIDEND booking first subtracts the existing
source-recorded `withholding_tax_amount`, then the resolved fee. BUY and INTEREST expense remain
outflows including the resolved fee; SELL, DIVIDEND, and INTEREST income must retain strictly
positive proceeds. Invalid zero or negative proceeds are rejected before writes with
`SELL_010_NON_POSITIVE_NET_SETTLEMENT`, `DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT`, or
`INTEREST_017_NON_POSITIVE_NET_SETTLEMENT`. Support diagnostics retain transaction, portfolio,
amount, and stable reason-code evidence without exposing raw payloads or infrastructure details.
Do not repair or reconcile such a case by applying `abs()` to the amount.

FX cash settlement is stricter because an inline charge has no unambiguous currency or charged leg.
The calculator rejects every non-zero resolved fee with `FX_025_NON_ZERO_EMBEDDED_FEE` and every
non-zero inline `withholding_tax_amount` with `FX_026_NON_ZERO_EMBEDDED_TAX` on
`FX_CASH_SETTLEMENT_BUY` or `FX_CASH_SETTLEMENT_SELL` before classification signing can apply
`abs()`. Zero inline charges remain compatible. Supported FX charges are distinct linked
`FEE`/`TAX` postings and therefore produce their own cashflow instead of netting or double counting
the FX leg.

For DIVIDEND, null/zero withholding preserves the prior gross-minus-fee result. Negative
withholding, withholding above gross, and withholding that consumes all settlement proceeds fail
closed. This is recorded-amount support, not withholding-rate derivation or jurisdiction-specific
tax advice. Other deductions, supplied-net identity, return-of-capital, basis reduction, and
advanced timing remain open under Core issue #448.

For an eligible booked transaction, the module:

1. validates replay and idempotency posture
2. resolves the effective processing transaction type
3. loads the governed cashflow rule for that transaction type
4. calculates an immutable normalized domain cashflow
5. maps that result to the existing cashflow row at the repository boundary
6. persists the row and stages the completion event

Every transaction emitted by the cost stage traverses this workflow. For `AUTO_GENERATE` booking,
that includes both the product transaction and its generated settlement cash leg. Both rows retain
position-flow classification because they belong to the same linked transaction group; the
settlement row is not a portfolio flow, which prevents cash-account movement from being counted as
external portfolio funding.

The service also keeps operational rule lookup supportable through cache refresh and invalidation
behavior rather than requiring a restart for every rule update. Rule writes, including upgrade and
downgrade migrations, advance `cashflow_rules.updated_at` so every worker observes the new rule-set
version before serving another fresh cache hit. Explicit invalidation acts on the runtime-owned
cache instance; there is no hidden process-global rule snapshot.

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

No active in-repo consumer waits for `cashflows.calculated` or `transactions.cost.processed`.
Transaction readiness is staged directly after cost, position, and cashflow effects succeed in the
same unit of work, so restoring a compatibility-event readiness consumer would reintroduce
redundant ordering and lag failure modes.

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
- [Portfolio Derived State](Timeseries-and-Aggregation)
- [Operations Runbook](Operations-Runbook)
- [Mesh Data Products](Mesh-Data-Products)
