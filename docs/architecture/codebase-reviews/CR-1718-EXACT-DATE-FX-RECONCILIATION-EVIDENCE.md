# CR-1718: Exact-Date FX Reconciliation Evidence

## Finding

The position-valuation control independently recomputed arithmetic but did not consume the FX
authority date already persisted on each daily snapshot. A historical snapshot carrying prior-date
FX evidence could therefore pass reconciliation when its arithmetic was internally consistent.

## Financial invariant

A persisted position valuation can pass the `position_valuation` control only when any recorded FX
authority date equals the snapshot business date. Reconciliation must assess the recorded source
fact, not query mutable FX tables for a replacement.

## Implementation

- `PositionValuationEvidence` carries the persisted `valuation_fx_rate_date` into the pure control
  policy.
- A non-null date different from the snapshot business date emits the stable ERROR finding
  `fx_rate_not_on_valuation_date`, preserving expected and observed dates.
- The finding routes to `VALUATION_OPERATIONS` with the bounded repair
  `REVALUE_POSITION_WITH_EXACT_DATE_FX`.
- The new finding composes with arithmetic and supported-receipt validation. The pre-existing
  missing bond quote-authority failure remains terminal because arithmetic and FX classification
  cannot authorize an unscoped bond quote.

Exact-date FX evidence passes. Null evidence preserves the existing same-currency and historical
legacy posture; classifying missing historical cross-currency lineage remains a separate #997
remediation boundary.

## Scope

This is one financial invariant in the financial-reconciliation ownership boundary. It does not
change APIs, OpenAPI, schemas, migrations, events, calculation formulas, dependencies, images,
datastores, runtime topology, HoldingsAsOf degradation, or replay behavior.

## Evidence

- Pure policy tests prove prior-date failure, exact-date success, and null/not-applicable behavior.
- Service tests prove the persisted snapshot field reaches the domain control and the finding is
  persisted with the governed repair recommendation.
- A PostgreSQL-backed API test proves a historically consistent snapshot with prior-date FX emits
  the durable finding and a failed reconciliation summary.
- Same-pattern search found one production construction of `PositionValuationEvidence`; it now maps
  the persisted date directly. No second FX lookup or control path was added.
- Protected PR and exact-main evidence remain pending.
