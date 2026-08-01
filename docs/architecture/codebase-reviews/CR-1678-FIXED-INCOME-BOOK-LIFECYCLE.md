# CR-1678: Fixed-Income Book Lifecycle

## Scope

This review governs the bounded fixed-income batch for GitHub issues #451, #478, #481, and #477,
with a partial contribution to #788. It covers explicit quote authority, amortized-cost evolution,
lot-disposal lineage, and maturity/call/partial-redemption economics in their required dependency
order.

## Findings

The authoritative valuation runtime had complete policy vocabulary but did not supply face principal
from persisted position evidence. Independent reconciliation accepted only authoritative unit-price
receipts. The scoped calculator therefore could not execute a valid percent-of-face assignment, and
the control plane rejected the same output even if it were produced.

The amortization RFC also contradicted its own roll-forward: its straight-line numerator made a
premium increase and a discount decrease. It left effective yield ambiguous between annual and
per-period interpretations, allowed broad fixed-income classification to imply eligibility, and did
not require authoritative clean acquisition cost even though the current BUY default can include
accrued interest in book cost.

Runtime review found three hard dependencies before redemption can be enabled:

- amortized cost must be effective-dated per source lot and must not overwrite tax/original lot cost;
- every disposal needs an immutable per-source-lot allocation receipt under #481;
- linked redemption product/principal-cash/optional-interest legs need a persisted canonical group
  sequence and correction identity; Kafka arrival order alone is not processing order.

## Corrections To Date

The scoped valuation path now binds persisted position quantity as face principal only when the exact
effective-dated assignment declares `FACE_AMOUNT`. Unit-price behavior remains distinct; factor and
independently supplied current-principal policies remain fail closed. A framework-free local
valuation-economics seam now owns scaling once, and independent reconciliation uses that seam for
supported unit-price, dirty percent-of-face, and clean no-periodic-accrual receipts. The shared seam
returns deterministic input/calculation/output lineage bound to the governed valuation numeric
policy, including when reconciliation consumes the local-currency result without source adapters.

RFC-AMORTIZATION-01 version 1.1 corrects straight-line direction, defines yield-application
conventions, requires clean-cost and exact-scope assignment authority, and makes unsupported profiles
park explicitly. The RFC ledger now reports this work truthfully as `target_state`; capability docs
and wiki remain `target_not_implemented` until the runtime is complete.

The transaction-processing domain now owns a framework-independent amortized-cost policy vocabulary.
It validates method/convention compatibility, policy identity and version, fee treatment, and
residual tolerance fail closed. Premium, discount, and par direction is derived from governed
opening book cost and redemption value rather than broad instrument labels. This is an additive
foundation only; it does not promote amortized cost to a supported runtime capability.

## Same-Pattern Review

The review covers both remaining `resolve_valuation_unit_price` call sites, authoritative price and
assignment correction paths, valuation receipts and Query projections, FIFO and average-cost lot
disposal, tax-lot consumers, transaction partitioning, linked-leg readiness, correction replay, and
the transaction capability registry. The legacy magnitude heuristic remains confined to explicitly
unscoped history; it cannot govern an authoritative receipt.

## Compatibility And Documentation

Existing unit-price results, snapshot fields, tax/original lot basis, and production-bookable
transaction types remain stable. `FACTOR_ADJUSTED_CURRENT_PRINCIPAL`, supplied current principal,
accrued-income variants without evidence, and every redemption type remain fail closed. No migration,
public API/OpenAPI, Kafka runtime, or capability claim has changed yet. The authored wiki is an
explicit no-change for this slice because it already states amortized cost and redemption are not
implemented.

## Validation

- signed commits `fb558698e`, `2ceec9e34`, `7f76491fe`, `fc79da648`, `47f059684`, and
  `3deb33d9b`;
- 35 warning-strict authoritative valuation tests;
- 49 warning-strict shared valuation/calculator tests;
- 77 warning-strict reconciliation domain/service/repository tests;
- 18 warning-strict amortized-cost policy tests;
- scoped Ruff lint/format, MyPy, RFC ledger, architecture-documentation, transaction-capability,
  wiki, JSON, calculated-output-policy, and diff-hygiene guards.

Protected PR, exact-main, migration, OpenAPI, runtime recovery, load, wiki publication, and issue
closure evidence remain pending until their corresponding implementation slices exist.
