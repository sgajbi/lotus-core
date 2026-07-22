# Transaction And Product Lifecycle Capabilities

This catalog states what `lotus-core` can book and calculate today across private-banking products,
transaction types, corporate actions, and lifecycle events. It is intended for client queries,
product decisions, support triage, downstream integration, and engineering change control.

The machine-readable source is
`contracts/transaction-processing/transaction-capability-catalog.v1.json`. Validate it with:

```powershell
make transaction-capability-catalog-guard
```

The guard compares every published transaction entry with the canonical runtime registry and
rejects missing codes, duplicate codes, metadata drift, unowned gaps, and missing documentation
anchors.

## Reading The Status

| Status | Meaning |
| --- | --- |
| `supported` | A dedicated production-bookable transaction type and implemented calculation posture exist. Product-level limitations may still apply. |
| `supported_via_generic_transaction_semantics` | Canonical legs can be represented through existing types such as `BUY`, `SELL`, `INTEREST`, or `DIVIDEND`; this does not certify every product-specific lifecycle event. |
| `limited` | Useful behavior exists, but one or more accounting, linkage, lineage, lifecycle, or calculation scenarios remain open and issue-owned. |
| `default_strategy` | The type is production-bookable but still uses a generic strategy; it must not be presented as fully specialized behavior. |
| `internal_generated` | Core generates the type internally; external production booking is disabled. |
| `target_not_implemented` | Vocabulary is reserved, but production booking and calculation are disabled. |
| `migration_only` | The type exists only to classify legacy input and is not a supported booking contract. |

## Registry Posture

The current registry contains 54 types.

| Registry status | Transaction types |
| --- | --- |
| `supported` | `BONUS_ISSUE`, `BUY`, `CASH_CONSIDERATION`, `CASH_IN_LIEU`, `CONSOLIDATION`, `DEMERGER_IN`, `DEMERGER_OUT`, `DEPOSIT`, `DIVIDEND`, `EXCHANGE_IN`, `EXCHANGE_OUT`, `FX_FORWARD`, `FX_SPOT`, `FX_SWAP`, `INTEREST`, `MERGER_IN`, `MERGER_OUT`, `REPLACEMENT_IN`, `REPLACEMENT_OUT`, `REVERSE_SPLIT`, `RIGHTS_ALLOCATE`, `RIGHTS_EXPIRE`, `RIGHTS_OVERSUBSCRIBE`, `RIGHTS_REFUND`, `RIGHTS_SELL`, `RIGHTS_SHARE_DELIVERY`, `RIGHTS_SUBSCRIBE`, `SELL`, `SPIN_IN`, `SPIN_OFF`, `SPLIT`, `STOCK_DIVIDEND`, `TRANSFER_IN`, `TRANSFER_OUT`, `WITHDRAWAL` |
| `limited` | `FEE`, `TAX` |
| `default_strategy` | `ADJUSTMENT`, `RIGHTS_ADJUSTMENT`, `RIGHTS_ANNOUNCE` |
| `internal_generated` | `FX_CASH_SETTLEMENT_BUY`, `FX_CASH_SETTLEMENT_SELL` |
| `migration_only` | `OTHER` |
| `target_not_implemented` | `ACCRETION`, `AMORTIZATION`, `CALL_REDEMPTION`, `CONVERSION_EVENT`, `CONVERSION_IN`, `CONVERSION_OUT`, `EXERCISE_IN`, `EXERCISE_OUT`, `MATURITY_REDEMPTION`, `PARTIAL_REDEMPTION`, `STRIKE_PAYMENT` |

A registry status describes transaction-engine posture. It is not by itself a claim that every
instrument using that transaction type has complete lifecycle coverage.

## Product And Lifecycle Matrix

| Product family | Lifecycle support | Status | Important limitation or issue |
| --- | --- | --- | --- |
| Listed equities, ETFs, bonds, funds, and structured instruments | Purchase and sale through `BUY` and `SELL` | `supported_via_generic_transaction_semantics` | Trade economics do not certify product-specific maturity, exercise, payoff, or distribution behavior. |
| Cash and deposits | Deposit, withdrawal, and interest through `DEPOSIT`, `WITHDRAWAL`, and `INTEREST` | `supported_via_generic_transaction_semantics` | No separately certified term-deposit maturity event. |
| Foreign exchange | Spot, forward, and swap | `supported` | Fee-currency policy remains under [#754](https://github.com/sgajbi/lotus-core/issues/754). |
| Listed funds | Subscription, redemption, distribution, and reinvestment through generic trade/income legs | `limited` | Mixed income and return-of-capital distribution is owned by [#448](https://github.com/sgajbi/lotus-core/issues/448). |
| Fixed income | Purchase, sale, coupon, and accrued-interest semantics | `supported_via_generic_transaction_semantics` | Amortized cost and redemption are separate unsupported lifecycles. |
| Fixed income | Maturity, call, and partial redemption | `target_not_implemented` | [#477](https://github.com/sgajbi/lotus-core/issues/477), [#481](https://github.com/sgajbi/lotus-core/issues/481) |
| Fixed income | Premium amortization and discount/OID accretion | `target_not_implemented` | [#478](https://github.com/sgajbi/lotus-core/issues/478) |
| Equity and fund distributions | Ordinary dividend | `limited` | Source-recorded withholding amount reduces settlement cash; rate derivation, full tax decomposition, return-of-capital, basis reduction, and timing remain under [#448](https://github.com/sgajbi/lotus-core/issues/448). |
| Equity corporate actions | Split, reverse split, consolidation, bonus issue, and stock dividend | `limited` | Parent-event persistence and complete lot lineage remain under [#480](https://github.com/sgajbi/lotus-core/issues/480) and [#481](https://github.com/sgajbi/lotus-core/issues/481). |
| Reorganizations | Merger, exchange, and replacement source/target legs | `limited` | Parent/dependency graph and lot lineage: [#480](https://github.com/sgajbi/lotus-core/issues/480), [#481](https://github.com/sgajbi/lotus-core/issues/481) |
| Partial reorganizations | Spin-off, demerger, mixed consideration, and fractional cash | `limited` | Full allocation, synthetic-flow, and lineage closure: [#450](https://github.com/sgajbi/lotus-core/issues/450), [#480](https://github.com/sgajbi/lotus-core/issues/480), [#481](https://github.com/sgajbi/lotus-core/issues/481), [#719](https://github.com/sgajbi/lotus-core/issues/719) |
| Rights issues | Announcement, allocation, sale, subscription, oversubscription, refund, expiry, adjustment, and share delivery | `limited` | Complete dependency, lineage, and unified-engine proof remains under [#480](https://github.com/sgajbi/lotus-core/issues/480), [#481](https://github.com/sgajbi/lotus-core/issues/481), and [#719](https://github.com/sgajbi/lotus-core/issues/719). |
| Securities transfers | Transfer in and transfer out | `limited` | Durable source-to-target lot lineage and all partial scenarios: [#481](https://github.com/sgajbi/lotus-core/issues/481), [#719](https://github.com/sgajbi/lotus-core/issues/719) |
| Convertibles, warrants, and options | Conversion, exercise, and strike payment | `target_not_implemented` | [#479](https://github.com/sgajbi/lotus-core/issues/479) |
| Structured products | Trade and generic coupon legs | `limited` | Observation, barrier, autocall, payoff, and physical settlement: [#758](https://github.com/sgajbi/lotus-core/issues/758) |
| Private markets | Commitment, capital call, contribution, distribution, return of capital, and recallable capital | `target_not_implemented` | [#759](https://github.com/sgajbi/lotus-core/issues/759) |
| Charges and tax | Fee and tax cash posting | `limited` | Component allocation and product attribution remain bounded by [#448](https://github.com/sgajbi/lotus-core/issues/448) and [#719](https://github.com/sgajbi/lotus-core/issues/719). |
| Corrections | Economic reversal, rebook, and restatement through adjustment semantics | `limited` | First-class cancellation and corporate-action correction state remain under [#480](https://github.com/sgajbi/lotus-core/issues/480) and [#719](https://github.com/sgajbi/lotus-core/issues/719). |

## Corporate Action Coverage

Core recognizes the following production-bookable corporate-action and rights transaction types:

1. full replacement: merger, exchange, and replacement source/target legs,
2. partial transfer: spin-off and demerger source/target legs,
3. mixed consideration: cash consideration and cash in lieu,
4. quantity restatement: split, reverse split, consolidation, bonus issue, and stock dividend,
5. rights lifecycle: announcement, allocation, sale, subscription, oversubscription, refund, expiry,
   adjustment, and share delivery.

This vocabulary is broader than full lifecycle certification. The current unified transaction
processing work owns typed validation and basis reconciliation for linked partial-transfer groups,
while [#480](https://github.com/sgajbi/lotus-core/issues/480) and
[#481](https://github.com/sgajbi/lotus-core/issues/481) retain the parent-event graph and durable
lot-lineage gaps.

## Accounting And Evidence Boundary

Core records source-owned economics and applies governed calculation policies. It must not infer a
jurisdiction-specific tax basis, issuer allocation, structured-product term, or private-market
capital classification when authoritative source evidence is absent. In particular:

1. cash receipt does not by itself mean income,
2. principal repayment and return of capital remain distinct from coupon or dividend income,
3. product and cash legs are linked but counted once at the governed cashflow level,
4. basis transfer and realized PnL require explicit source facts and reconciliation,
5. unsupported lifecycle events fail closed or remain production-booking disabled.

## Client And Support Use

For a client query, answer at three levels:

1. **Transaction type:** Is the canonical code production-bookable?
2. **Lifecycle:** Is the requested event implemented, generic-only, limited, or disabled?
3. **Evidence:** Which RFC, test, contract, and open issue proves the answer?

Do not answer “supported” solely because an instrument can be bought or sold. For example, a
structured note can use `BUY`, `SELL`, and `INTEREST`, while barrier observation and maturity payoff
remain unimplemented product lifecycles.

## Maintenance

When transaction registry truth changes:

1. update implementation and focused tests,
2. run `python scripts/transaction_processing/generate_capability_catalog.py`,
3. update product-lifecycle rows and gap issue ownership,
4. update this page and `wiki/Transaction-and-Product-Lifecycle-Capabilities.md`,
5. run `make transaction-capability-catalog-guard`,
6. publish the repo-local wiki source after merge.
