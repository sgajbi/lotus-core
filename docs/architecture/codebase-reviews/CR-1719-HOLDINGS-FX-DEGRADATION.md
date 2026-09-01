# CR-1719 HoldingsAsOf FX Degradation

## Scope

Issue #997, bounded to the Query Service `HoldingsAsOf:v1` position-response boundary. Historical
row repair, valuation replay/restatement orchestration, cash reporting-currency conversion, and
broad tenant work are outside this tranche.

## Financial Invariant

A returned cross-currency position valuation is not current source evidence unless the persisted
FX authority date used to calculate it equals the HoldingsAsOf response date. Query Service must
classify the durable valuation evidence; it must not query today's mutable FX table to reconstruct
or replace historical truth.

## Finding

Position valuation and reconciliation already persisted and consumed
`DailyPositionSnapshot.valuation_fx_rate` and `valuation_fx_rate_date`. Holdings assembly still
considered only position-state and market-price freshness, so a historical carried-FX valuation
could be returned with complete/current source posture.

The fallback path for a history-backed position also copied valuation amounts from a durable
snapshot without carrying that snapshot's FX authority fields into the quality decision.

## Implementation

1. Both snapshot-fallback repository queries now select and return the persisted valuation-time
   source/reporting currencies, `valuation_fx_rate`, and `valuation_fx_rate_date` with the
   valuation amounts they support.
2. Holdings assembly builds one normalized security-to-FX-date map only for valuations that
   actually used FX. Direct snapshot rows and snapshot-backed history supplements follow the same
   policy.
3. A date different from the response as-of date makes source quality `STALE` and emits
   row/field-scoped `FX_RATE_STALE`, preserving the recorded source date.
4. A used FX rate whose durable date is absent emits fail-closed `FX_RATE_EVIDENCE_MISSING` with
   unavailable degradation posture.
5. Exact-date FX evidence and valuations with no persisted FX rate retain existing behavior.

## Contract And Failure Semantics

The response schema is unchanged: the existing `SourceDataDegradationSummary` carries the new
stable reasons. `FX_RATE_STALE` affects local market value, local unrealized P&L, and unrealized FX
P&L fields. The deterministic HoldingsAsOf content hash already includes data quality and complete
degradation details, so a corrected/restated FX authority date changes response identity without a
new competing receipt.

## Same-Pattern Review

The scan covered every production call to `holdings_data_quality_status` and
`holdings_degradation_summary`, both snapshot-valuation fallback queries, and the sole
`portfolio_holdings_response` assembly path. Cash reporting-currency restatement owns a separate
request-time FX policy and is not a persisted position-valuation authority.

## Evidence

- 77 focused Query Service policy, orchestration, read, and repository tests pass warning-strict.
- Direct tests prove exact-date, prior-date, missing-date, same-currency/no-FX, direct-snapshot, and
  snapshot-backed fallback behavior.
- Repository query-shape tests prove both fallback paths select and map the persisted FX fields.
- Scoped Ruff and full MyPy pass.
- Broader repository-native gates, PR review/CI, and exact-main evidence are required before the
  tranche can be called complete.

## Documentation Decision

The implementation-backed HoldingsAsOf methodology, repository engineering context, codebase
review ledger, and `Mesh-Data-Products` wiki source change in this tranche. Publish and verify wiki
parity only after merge.
