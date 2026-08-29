# CR-1715: Portfolio Snapshot Effective-Date Authority

## Finding

`PortfolioStateSnapshot:v1` published stable values and calculation lineage but did not preserve
the independent source-owned dates for portfolio state and market-data evidence. A downstream
consumer could therefore only stamp the caller's requested date onto both source families. That
produced a plausible date, not authoritative financial evidence.

## Financial invariant

A governed valuation date is supportable only when Core can prove:

1. every selected portfolio row has one coherent business date;
2. every material valued row, projected price, and non-identity FX observation has one coherent
   market-data date;
3. the portfolio and market-data dates agree; and
4. the agreed date equals the requested business date.

Request fields and generation time are scope and operational evidence. They are never substitutes
for source-effective dates.

## Implementation

- `ResolvedFxRate` and projected-position resolution retain exact source dates without attaching a
  fabricated date to same-currency identity conversion.
- `DailyPositionSnapshot` persists the actual FX effective date and exact rate used by
  cross-currency valuation. The database enforces their atomicity and positive finite value;
  legacy rows without that lineage and carried-forward rates fail closed until revaluation.
- One QCP application policy resolves source-family dates, deterministic hashes and snapshot ids,
  freshness, readiness, and stable failure reasons.
- `CoreSnapshotResponse` publishes a typed `lotus.source-provenance.v1` envelope and an explicit
  valuation supportability result.
- Source provenance is bound into input lineage, response content identity, and runtime lineage;
  same-date FX corrections change market-data identity without conflating holdings changes.
- `source_evidence_current` additionally requires valuation supportability `READY`.

Historical cost-basis fallback, missing valued rows, mixed dates, current-price rows with missing
FX lineage, and carried-forward price or FX evidence remain unavailable. No test timeout,
assertion, quality gate, or failure mapping was weakened.

The required persisted FX fact adds nine lines to the legacy shared ORM module's exact
source-size ceiling under #1035; #462 remains the owner of its decomposition. The same branch banks
a 13-line reduction in the oversized QCP integration router, so aggregate governed exception size
still decreases and neither baseline receives headroom.

## Proof

Focused proof covers:

- exact coherent date readiness and stable identity under input reordering;
- missing, mixed, stale, historical-fallback, carried-forward, and same-date-corrected evidence;
- projected price and FX date propagation;
- service lineage and current-evidence classification;
- recursive OpenAPI documentation; and
- canonical `PB_SG_GLOBAL_BAL_001` route serialization without field loss.

Downstream `lotus-advise#557` must adopt this aggregated Core contract and retain the envelope
through proposal persistence before live memo/report-package acceptance evidence can close.
