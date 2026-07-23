# Transaction And Product Lifecycle Capabilities

This page answers which private-banking products, transaction types, corporate actions, and
lifecycle events `lotus-core` handles today. It is designed for client, sales, support, operations,
product, and engineering questions.

## Evidence And Scope

Implementation truth is governed by
`contracts/transaction-processing/transaction-capability-catalog.v1.json` and checked by:

```powershell
make transaction-capability-catalog-guard
```

The detailed engineering catalog is
[Transaction And Product Lifecycle Capabilities](../docs/features/transaction-and-product-lifecycle-capabilities.md).

## Current Position

Core has 54 registered transaction types:

| Registry posture | Count | Meaning |
| --- | ---: | --- |
| `supported` | 35 | Dedicated production-bookable semantics exist. |
| `limited` | 2 | Production booking exists with explicit calculation limits. |
| `default_strategy` | 3 | Production booking uses a generic strategy. |
| `internal_generated` | 2 | Core creates these types; clients cannot book them directly. |
| `migration_only` | 1 | Legacy classification only. |
| `target_not_implemented` | 11 | Reserved vocabulary; production booking is disabled. |

Transaction-level support is not the same as complete product-lifecycle support. A product may be
bought and sold while its maturity, exercise, barrier, payoff, or capital-call lifecycle remains
unsupported.

## Client Capability Matrix

| Product or lifecycle | Current support | Client-safe answer | Open gap |
| --- | --- | --- | --- |
| Listed equity, ETF, bond, fund, or structured-instrument purchase/sale | Generic `BUY` and `SELL` semantics | Core records canonical acquisition/disposal economics; product-specific events require separate confirmation. | Product lifecycle rows below |
| Cash and deposit funding, withdrawal, and interest | Generic cash and interest semantics | Core records principal cash movements and interest; no dedicated term-deposit maturity event is certified. | None currently claimed |
| FX spot, forward, and swap | Supported | Core models linked FX contract/cash legs; non-zero embedded fees and withholding taxes fail closed and supported fees/taxes are separate linked postings. | Future embedded-charge support requires explicit charge currency and charged-leg ownership. |
| Listed fund subscription/redemption/distribution/reinvestment | Limited | Generic trade and distribution legs work; mixed return-of-capital handling is not complete. | [#448](https://github.com/sgajbi/lotus-core/issues/448) |
| Bond purchase, sale, coupon, and accrued-interest semantics | Generic support | Core handles generic trade and coupon legs. | Amortized cost and redemption below |
| Bond maturity, call, or partial redemption | Not implemented | Production booking is disabled. | [#477](https://github.com/sgajbi/lotus-core/issues/477), [#481](https://github.com/sgajbi/lotus-core/issues/481) |
| Premium amortization and discount/OID accretion | Not implemented | No production amortized-cost schedule is certified. | [#478](https://github.com/sgajbi/lotus-core/issues/478) |
| Ordinary dividend | Limited | Ordinary income and source-recorded withholding-amount settlement work; withholding-rate derivation, full tax decomposition, return-of-capital, and basis reduction do not. | [#448](https://github.com/sgajbi/lotus-core/issues/448) |
| Split, reverse split, consolidation, bonus issue, stock dividend | Limited | Transaction semantics exist; complete event and lot-lineage evidence remains open. | [#480](https://github.com/sgajbi/lotus-core/issues/480), [#481](https://github.com/sgajbi/lotus-core/issues/481) |
| Merger, exchange, replacement | Limited | Source/target transaction semantics exist; parent graph and lot lineage remain open. | [#480](https://github.com/sgajbi/lotus-core/issues/480), [#481](https://github.com/sgajbi/lotus-core/issues/481) |
| Spin-off, demerger, mixed consideration, cash in lieu | Limited | Linked validation and basis reconciliation exist; all allocation and lineage scenarios are not closed. | [#450](https://github.com/sgajbi/lotus-core/issues/450), [#480](https://github.com/sgajbi/lotus-core/issues/480), [#481](https://github.com/sgajbi/lotus-core/issues/481) |
| Rights issue lifecycle | Limited | Core recognizes announcement through delivery vocabulary; full event/lineage proof remains open. | [#480](https://github.com/sgajbi/lotus-core/issues/480), [#481](https://github.com/sgajbi/lotus-core/issues/481), [#719](https://github.com/sgajbi/lotus-core/issues/719) |
| Transfer in/out | Limited | Position and basis semantics exist; complete source-to-target lot lineage remains open. | [#481](https://github.com/sgajbi/lotus-core/issues/481), [#719](https://github.com/sgajbi/lotus-core/issues/719) |
| Convertible conversion, warrant/option exercise, strike payment | Not implemented | Reserved codes are production-booking disabled. | [#479](https://github.com/sgajbi/lotus-core/issues/479) |
| Structured-product coupon, observation, barrier, autocall, payoff | Limited | Generic trade/coupon legs work; observation, barrier, autocall, payoff, and physical settlement do not. | [#758](https://github.com/sgajbi/lotus-core/issues/758) |
| Private-market commitment, capital call, distribution, return of capital | Not implemented | Generic cash/dividend entries must not be presented as commitment lifecycle support. | [#759](https://github.com/sgajbi/lotus-core/issues/759) |
| Fee and tax cash postings | Limited | Cash posting exists; attribution and jurisdiction-specific tax treatment remain policy-bounded. | [#448](https://github.com/sgajbi/lotus-core/issues/448), [#719](https://github.com/sgajbi/lotus-core/issues/719) |
| Economic reversal and rebook | Limited | Correction can be represented economically; first-class cancellation and corporate-action correction remain open. | [#480](https://github.com/sgajbi/lotus-core/issues/480), [#719](https://github.com/sgajbi/lotus-core/issues/719) |

## Production-Disabled Types

These codes are registered for target design but cannot be booked in production:

`ACCRETION`, `AMORTIZATION`, `CALL_REDEMPTION`, `CONVERSION_EVENT`, `CONVERSION_IN`,
`CONVERSION_OUT`, `EXERCISE_IN`, `EXERCISE_OUT`, `MATURITY_REDEMPTION`, `PARTIAL_REDEMPTION`,
and `STRIKE_PAYMENT`.

## Corporate Actions Recognized By Core

Core recognizes transaction vocabulary for:

1. merger, exchange, and replacement source/target legs,
2. spin-off and demerger source/target legs,
3. cash consideration and cash in lieu,
4. split, reverse split, consolidation, bonus issue, and stock dividend,
5. rights announcement, allocation, sale, subscription, oversubscription, refund, expiry,
   adjustment, and share delivery.

These types are production-bookable, but the matrix above identifies where complete parent-event,
dependency, partial-allocation, synthetic-flow, correction, or lot-lineage proof remains open.

## Evidence Rule

Use the machine catalog for exact status and issue ownership. Do not infer that:

1. cash receipt is income,
2. principal repayment is a coupon,
3. return of capital is a dividend,
4. an instrument's `BUY`/`SELL` support certifies its full lifecycle,
5. target registry vocabulary is production functionality.

For broader service boundaries and safe claims, continue to [Supported Features](Supported-Features).
