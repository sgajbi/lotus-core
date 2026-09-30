# Shared Requirement: Common Calculation Conventions

## Purpose

Define shared calculation rules that apply across transaction types.

## Numeric Rules

- all business-critical numeric values must use decimal-safe arithmetic
- floating-point arithmetic must not be used for financial calculations
- precision and rounding must be policy-driven and documented

## Base and Local Currency

Each transaction RFC must define:

- local amount fields
- base amount fields
- fx source
- fx precision and rounding

`transaction_fx_rate` is quoted as trade-currency units translated into portfolio-base-currency
units. A positive rate supplied by the booking source is immutable cost authority for the product
transaction and its generated settlement cash leg. Cost enrichment consults effective-dated
reference FX only when that source field is absent; ordinary replay preserves the rate already
booked on a generated leg. An authorized source correction may replace the source-booked rate
explicitly; an authorized correction of reference-derived economics may rederive the settlement
cash basis, while ordinary replay freezes the existing generated rate.

Core records the server-owned origin as `SOURCE_BOOKED`, `REFERENCE_DERIVED`, or
`LEGACY_UNKNOWN`; clients cannot assert this provenance. Only `SOURCE_BOOKED` FX is part of source
semantic identity. Legacy rows remain explicitly unknown rather than being inferred. A supplied
same-currency trade/base rate must equal `1` or processing rejects it. When normalized reference
rows share an effective date, product and settlement selection both use stable repository date/id
order and select the final eligible row.

New source-booked raw events use the v2 identity that includes FX; v1 remains only a compatibility
candidate for historical rows. A mixed-version late writer may leave a non-null FX rate with a null
origin. Core accepts that narrow replay only when the locked v1 processed-event fence, tenant,
portfolio, all v1 economics, and numeric FX exactly match the locked durable transaction. It does
not infer or promote historical authority; any mismatch remains a semantic conflict.
Processing uses a separate FX-sensitive v2 identity for source-booked rates. Rolling compatibility
is read-only and accepts only an exact pre-existing v1 physical fence; it never creates a v1 fence
while probing. An omitted cash-entry mode canonicalizes to the governed transaction-type default,
while an explicit upstream mode remains distinct.

The provenance migration requires a bounded writer-quiescence cutover: drain transaction
persistence and processing writers, clear long-running database transactions, apply the migration
once under its five-second lock timeout, then resume writers and reconcile delayed deliveries. A
lock timeout is a failed attempt to retry after quiescence, never permission for concurrent DDL.

When source FX is absent and settlement occurs on a different date, the product cost uses the
latest supported reference rate effective on or before trade date while the generated cash basis
uses the equivalent rate effective on or before settlement date. Same-currency economics use `1`.
Valuation continues to use its separately governed effective-date/reference policy and must not
rewrite historical booked cost.

A generated cash leg is admitted only after Core resolves the active cash-account mapping within
the admitted tenant, portfolio, and settlement-date window. That mapping owns the cash security and
account currency; an optional source `settlement_cash_instrument_id` must match it. The mapped
instrument must exist, be classified as `CASH`, and have the same currency as both the account and
transaction trade currency. Missing authority is retryable; mapping, classification, or currency
mismatch is rejected before child persistence. The resolved security is derived settlement context
and does not rewrite the source transaction or its identity. Generated local and base costs are
normalized with the governed transaction-ledger 18,10 output policy.

Deployment does not rewrite historical generated cash legs. Operators must identify affected
transactions from source lineage, validate the authoritative booked FX, and use the governed
transaction correction/replay workflow to rebuild those economics; direct database repair is not
a supported remediation path.

## Required Explicitness

If a transaction produces realized pnl, the transaction RFC must define both:

- realized capital pnl
- realized fx pnl

If a transaction does not realize pnl, the RFC must define whether those fields are explicit zero values or not applicable.

## Formula Rule

Every transaction RFC must define:

- input values
- derived values
- formula order
- default formulas
- policy-driven variants

## Settlement Cash Rule

For ordinary BUY, SELL, DIVIDEND, and INTEREST transactions, one domain policy must resolve the
transaction fee, signed settlement amount, and ledger direction. Fee components take precedence
over the aggregate `trade_fee` when any component is present.

```text
buy settlement = -(gross amount + resolved transaction fee)
sell settlement = gross proceeds - resolved transaction fee
dividend settlement = gross dividend - resolved transaction fee
interest income settlement = pre-fee net interest - resolved transaction fee
interest expense settlement = -(pre-fee net interest + resolved transaction fee)
```

SELL, DIVIDEND, and INTEREST income settlement must remain strictly positive before the inflow sign
is applied. A zero or negative result is a hard rejection; absolute-value normalization must not
turn it into an apparent inflow. Generated cash legs and persisted product cashflows must consume
the same signed settlement result.

The current ordinary DIVIDEND runtime treats booked `gross_transaction_amount` as available
proceeds for this fee boundary. It does not claim that gross amount is the canonical final net
dividend after withholding tax or return-of-capital decomposition; that separate migration remains
tracked by GitHub issue #448.
