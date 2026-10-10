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
booked on a generated leg. Replacing source-booked FX requires separately qualified economic
supersession; the evidence-confirmation command does not provide it. Application repair can
rederive reference-derived settlement cash basis from corrected source authority, while ordinary
replay freezes the existing generated rate. Neither capability authorizes direct database repair
as an operator workflow.

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

### Booked Cost and Valuation FX Attribution

The implemented position-valuation convention translates the local price component at
valuation-date FX and assigns retranslation of historical local cost to the FX component.
This is Core position economics, not a time-weighted performance attribution methodology.
For one position, define:

| Symbol | Source and units |
| --- | --- |
| `C_local` | Persisted historical local cost basis, in instrument currency |
| `C_base` | Persisted historical cost basis, in portfolio base currency |
| `M_local` | Quantity times the valuation price aligned to instrument currency |
| `X_value` | Valuation FX, portfolio-base units per one instrument-currency unit |

Before ledger output normalization:

```text
M_base = M_local * X_value
total_PnL_base = M_base - C_base
FX_PnL_base = C_local * X_value - C_base
price_PnL_base = total_PnL_base - FX_PnL_base
```

`POSITION_VALUATION_LEDGER_OUTPUT_V1` normalizes market values and FX P&L, then derives
price P&L from normalized total minus normalized FX P&L. Any ledger rounding residual
therefore belongs to price P&L; the persisted decomposition conserves total P&L exactly.
Do not reconstruct historical base cost from current reference FX.

For a BUY of 10 units at 100 XTS with supplied XTS/USD `2`, local cost is 1000 XTS and
base cost is 2000 USD even when the trade-date reference rate is `2.5`. At local market
value 1100 XTS and valuation FX `2.5`, market value is 2750 USD: price P&L is 250 USD,
FX P&L is 500 USD, and total P&L is 750 USD. A valuation FX correction to `3` changes
these to market value 3300 USD, price P&L 300 USD, FX P&L 1000 USD and total P&L
1300 USD, without changing either historical cost basis.

The authority cases are intentionally distinct:

| Input or change | Cost-authority outcome |
| --- | --- |
| Positive supplied rate, conflicting or missing reference | Preserve supplied rate; reference lookup is unnecessary for cost enrichment |
| Absent supplied rate | Derive latest reference effective on or before the economic leg date; mark `REFERENCE_DERIVED` |
| Absent supplied rate and no eligible reference | Retryable missing-FX failure; do not default cross-currency cost to `1` |
| Zero, negative or non-finite supplied rate | Public transaction admission rejects it |
| Same trade/base currency | Identity `1`; reject a supplied non-unit rate |
| Later-effective reference delivered before an earlier transaction | Never select a future-effective row; arrival order is not business-date authority |
| Reference correction | May change valuation; does not supersede `SOURCE_BOOKED` cost |
| Authorized source transaction correction | Requires separately qualified economic-supersession authority; ordinary redelivery and evidence confirmation cannot replace booked FX |

The current `POST /ingest/transactions/{transaction_id}/source-evidence` command confirms
missing source evidence under the contract owned by issues #1176/#1004. It preserves the
original transaction economics; its successful completion does not authorize an FX-rate
replacement. The PostgreSQL regression
`test_source_booked_fx_only_correction_is_material_and_idempotent` deliberately updates the
stored source row before invoking application repair. It proves material recalculation and
idempotency at that boundary, not a supported HTTP economic-correction workflow. The original
#1155 conditional economic-supersession requirement remains a separately assessed dependency;
do not use that regression or the evidence-confirmation route to claim it satisfied.

The same-date conflict, backdated lot rebuild and disposal example are exercised by
`test_source_booked_fx_governs_product_and_generated_cash_basis` in the combined FX
PostgreSQL integration module. Its direct application/database boundary is not HTTP ingress.
The supported HTTP valuation-correction/replay/query-process-restart scenario is separately
owned by `test_booked_fx_cash_reference_correction_replay_and_process_restart`. It admits
source-booked FX `2` against trade-date reference `2.5` and requires fixed 2000/-2000 base
costs for the equity/cash pair. Execution evidence must match this exact scenario revision;
earlier versions seeded equal booking-date/reference FX and do not prove the conflict.
The named component regression `test_source_booked_fx_rate_is_not_replaced_by_reference_rate`
must reject restoration of unconditional reference overwrite. Evidence from these scopes must
not be promoted into provider, downstream, full-window performance or production certification.

### Funded Cash, Fees and Settlement Dates

For ordinary generated settlement legs, `trade_fee` is an amount in trade currency, not a
separately denominated fee. BUY cash outflow includes the fee; SELL, DIVIDEND and income INTEREST
cash inflows deduct it. The generated child has zero fee, so replay cannot charge it again.
There is no ordinary generated-leg fee-currency conversion field or supported third-currency
fee conversion in this contract. A separately booked FX-linked FEE has its own authority and
does not demonstrate that capability. Cash-account, mapped instrument and trade currencies must
agree; FX never repairs a mismatched account mapping.

The supported HTTP scenario above also defines this independent positive-cash book. Deposit
2000 XTS before the original BUY; retain booked FX2 and value both positions at FX3, with equity
price110 and cash price1. Fees are 2 XTS on each additional source transaction. Amounts below are
USD; historical base basis does not use valuation FX3.

| Cumulative source cut | Equity basis | Cash basis | Equity mark | Cash mark | Total unrealized P&L |
| --- | --- | --- | --- | --- | --- |
| Funded original BUY10 at100 | 2000 | 2000 | 3300 | 3000 | 2300 |
| BUY1 at100 plus fee2 | 2204 | 1796 | 3630 | 2694 | 2324 |
| SELL5 at110 less fee2 | 1204 | 2892 | 1980 | 4338 | 2222 |
| DIVIDEND100 less fee2 | 1204 | 3088 | 1980 | 4632 | 2320 |
| Income INTEREST50 less fee2 | 1204 | 3184 | 1980 | 4776 | 2368 |

FIFO SELL consumes 500 XTS/1000 USD of original acquisition cost. Net proceeds are 548 XTS/
1096 USD, so realized P&L is 48 XTS/96 USD. Original BUY and fee-bearing BUY settle on their
trade dates; SELL and both income legs settle on the next business date. Each generated child
uses settlement date and preserves source-booked FX2 even though that date's valuation FX is3.
The source commands, actual settlement builder and adverse literal-oracle controls have focused
unit coverage. Actual HTTP/worker/PostgreSQL execution of these added stages requires fresh
hosted evidence for this source revision; collection or older fixture execution is insufficient.
After final funded replay, the scenario restarts only its already-owned query process, then uses
a fresh HTTP client to require identical final holdings/content hash and all11 linked source/cash
rows, including SELL realized48 XTS/96 USD. It retains process-generation and HTTP response
receipts. This is query-process durability evidence, not a PostgreSQL restart claim.

An independent USD-base/USD-instrument/USD-cash control uses booked identity1 and admits no FX
rate rows. After funding2000 USD and BUY10 at100 USD, both bases are1000 USD; day-two equity
mark1100 and cash mark1000 imply total mark2100 and unrealized P&L100. Both FX components must
be zero, and exactly one generated cash child must remain linked to the BUY. This control uses
the supported ingestion/query paths in the same registered scenario, not a rescaled foreign-FX
response. Its hosted execution is required independently of the component controls.

The same scenario first withholds the day-two exact valuation fixing. It requires null base
valuation and `VALUATION_CURRENCY_LINEAGE_MISSING` on the public holdings response, plus actual
latest-epoch valuation jobs for both securities in `FAILED` state with the exact missing-date FX
reason, before supplying the fixing and checking recovery. This distinguishes a missing FX cause
from unrelated degradation; booked cost remains unchanged throughout.

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
