# CR-1710 Cash Instrument Settlement Authority

Date: 2026-08-25

Status: Fixed-local candidate; protected PR review, CI, exact-main validation, issue closure, and
branch/worktree hygiene remain pending.

Issue: #1008

## Finding

Cash-account transaction handling inferred cash classification from identifier prefixes in cost
calculation and ordering. A security-tagged `FEE` or `TAX` could therefore reach generic cost and
position paths and create financially false cash state. Missing instrument classification also had
no single fail-closed settlement boundary.

## Financial-System Invariant

Transaction type identifies intended economics; it does not prove instrument identity. Every
registry `cash_account_required` booking must use server-owned instrument product metadata as its
cash authority before any financial mutation. Missing or non-cash authority must reject
deterministically, leave no position, cashflow, readiness, or outbox effect, and remain safe under
retry and replay.

## Design

1. One shared pure-domain predicate classifies cash only from normalized `product_type` and
   `asset_class`; transaction processing and analytics consume the same policy.
2. One registry-driven validator covers all public and internal generated cash-account types and
   emits stable missing-authority and non-cash reason codes.
3. Processing invokes the validator after repository enrichment and maps failures into governed
   retryable/non-retryable application errors with source-safe detail.
4. Cost calculation validates independently, including historical rebuild rows by their effective
   FX component type, and no longer assigns generic strategies to public cash-account transaction
   types. Ordering uses the same metadata predicate.
5. Position reduction rejects booked-cost signs that contradict cash inflow/outflow economics.
6. A CI architecture guard scans all production service source and rejects instrument/security
   identifier-prefix cash inference. The same-pattern scan removed the remaining Query Control
   Plane analytics fallback. Analytics now projects both authoritative product type and asset class,
   preserving valid cash instruments when either supported metadata field is absent.

## Meaningful Proof

Table-driven domain tests cover every registry-owned cash-account type, all four public booking
types, missing and non-cash authority, identifier-prefix impersonation, and valid generated FX cash
legs. The #731 security-tagged-fee scenario is preserved in a governed golden vector pack.
Application tests prove rejection occurs before downstream modules and that the unit of work rolls
back without commit. Cost and position tests prove no positive default cost or contradictory cash
balance can be materialized. Rebuild tests prove persisted FX cash buy/sell components cannot bypass
the fence through their business transaction type. Analytics tests prove `product_type=CASH` with a
null asset class retains internal cash-book beginning-value semantics while cash-prefixed securities
remain non-cash.

## Compatibility And Scope

No API/OpenAPI, event/Kafka, schema/migration, dependency, image, datastore, or runtime-topology
contract changed. Valid cash-account bookings retain their economics. Invalid or unclassifiable
bookings intentionally change from permissive processing to deterministic rejection. No wiki
change is required because the capability catalog and repository engineering context own this
engineering and product-support truth.
