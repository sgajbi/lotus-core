# CR-1720 HoldingsAsOf Valuation-Currency Lineage

## Scope

Issue #997, bounded to persisted valuation-currency evidence classification at the Query Service
`HoldingsAsOf:v1` response boundary. Historical replay/backfill, reconciliation policy, runtime
restatement certification, schema changes, and broad tenant work are outside this tranche.

## Financial Invariant

Core cannot certify a persisted valuation as complete unless its durable source and reporting
currencies prove whether FX translation was required. Current instrument or portfolio master data
must not relabel historical valuation evidence.

## Finding

The previous holdings FX classifier correctly handled complete cross-currency pairs, including
stale and missing FX dates, but treated a missing currency pair as proof that no FX was required.
Rows created before valuation-currency lineage was persisted could therefore remain eligible for a
`COMPLETE` response even though Core could not explain the currency basis of their translated
values. The same ambiguity existed for snapshot values supplementing position-history rows.

## Implementation

1. Holdings assembly returns both the persisted FX-date map and the normalized security identities
   whose selected valuation evidence lacks either currency.
2. Missing or partial currency lineage reduces source quality to `UNKNOWN` before a response can be
   certified complete.
3. Row-scoped degradation uses stable reason `VALUATION_CURRENCY_LINEAGE_MISSING`, unavailable
   source posture, and no invented source date.
4. Only translated portfolio-base market value and unrealized P&L fields are marked affected;
   local instrument-currency values are not FX-derived.
5. Complete same-currency pairs require no FX fact. Complete cross-currency pairs retain exact-date,
   stale-date, and missing-rate behavior from the preceding #997 tranches.

## Same-Pattern Review

The scan covered the sole HoldingsAsOf response assembly, direct snapshot selection, both
snapshot-backed history fallback queries, and all callers of holdings quality/degradation policy.
QCP already fails closed when valuation currency evidence is absent and was not changed.
Financial-reconciliation missing-lineage policy and historical replay are separate ownership
boundaries and are not silently absorbed here.

## Evidence

- Pure evidence classification tests cover exact cross-currency FX, missing required FX,
  same-currency identity, all-null legacy lineage, partial lineage, and history fallback.
- Quality and degradation tests prove typed unknown behavior and exact affected fields.
- Response orchestration proves an otherwise current/reconciled legacy row cannot become complete.
- Focused repository-native Query Service, lint, type, architecture, documentation, and required CI
  gates are required before merge.

## Compatibility

No API shape, persisted value, schema, migration, event, OpenAPI, dependency, or runtime topology
changes. Only source-quality metadata becomes more conservative for ambiguous historical rows.
