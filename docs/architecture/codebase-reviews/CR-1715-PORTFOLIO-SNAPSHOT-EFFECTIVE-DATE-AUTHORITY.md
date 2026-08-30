# CR-1715: Portfolio Snapshot Effective-Date Authority

## Finding

`PortfolioStateSnapshot:v1` published stable values and calculation lineage but did not preserve
the independent source-owned dates for portfolio state and market-data evidence. A downstream
consumer could therefore only stamp the caller's requested date onto both source families. That
produced a plausible date, not authoritative financial evidence.

## Financial invariant

A governed valuation date is supportable only when Core can prove:

1. every selected current row has one coherent daily valuation-snapshot date, while its
   per-security last-mutation date remains lineage rather than valuation-date authority;
2. every material valued row, projected price, and non-identity FX observation has one coherent
   market-data date;
3. the portfolio and market-data dates agree; and
4. the agreed date equals the requested business date.

Request fields and generation time are scope and operational evidence. They are never substitutes
for source-effective dates.

## Implementation

- `ResolvedFxRate` and projected-position resolution retain exact source dates without attaching a
  fabricated date to same-currency identity conversion.
- `DailyPositionSnapshot` persists the source and reporting currencies used by valuation plus the
  actual FX effective date and exact rate used by cross-currency valuation. The database enforces
  canonical currency-pair atomicity and positive finite FX evidence; legacy rows without that
  receipt and carried-forward rates fail closed until revaluation.
- One QCP application policy resolves source-family dates, deterministic hashes and snapshot ids,
  freshness, readiness, and stable failure reasons.
- Current snapshot mode derives portfolio effective time from the daily valued-position snapshot
  date. Per-security position-history dates remain mutation and reconciliation evidence, and the
  daily snapshot date is included in portfolio source identity so consecutive valuation days cannot
  publish the same deterministic provenance id. Historical fallback omits the snapshot-only hash
  field, preserving its established mutation-date source identities.
- `CoreSnapshotResponse` publishes a typed `lotus.source-provenance.v1` envelope and an explicit
  valuation supportability result.
- Source provenance is bound into input lineage, response content identity, and runtime lineage;
  same-date FX corrections change market-data identity without conflating holdings changes.
- Baseline positions and market-data lineage use the persisted valuation-time currency pair, not
  mutable current instrument master data. A later instrument-currency correction therefore cannot
  relabel historical price or FX evidence; a changed portfolio reporting currency fails closed
  until the position is revalued in that reporting context.
- Portfolio and market-data provenance timestamps are derived independently. Portfolio timestamps
  come from the selected current-epoch position facts; market-data timestamps come from the
  persisted valuation snapshot plus each price and non-identity FX observation actually used.
  Re-observing market evidence can therefore advance only the market timestamp without rewriting
  portfolio evidence or changing value-based source identity.
- `source_evidence_current` additionally requires valuation supportability `READY`.

Historical cost-basis fallback, incomplete local or reporting values, mixed daily snapshot dates,
current-price rows with missing FX lineage, and carried-forward price or FX evidence remain
unavailable. No test timeout, assertion, quality gate, or failure mapping was weakened.

The complete persisted valuation receipt adds 23 lines to the legacy shared ORM module's exact
source-size ceiling under #1035; #462 remains the owner of its decomposition. The same branch banks
a 13-line reduction in the oversized QCP integration router. The tracked exception total therefore
increases by ten necessary lines without adding headroom: both files remain exact-ratcheted, and
future growth or stale baselines fail the source-size gate.

## Proof

Focused proof covers:

- exact coherent date readiness and stable identity under input reordering;
- multi-security daily snapshots with distinct last-mutation dates, and distinct portfolio source
  identities for consecutive daily valuation snapshots;
- the historical fallback's established source hash and id remain unchanged;
- missing, mixed, stale, historical-fallback, carried-forward, and same-date-corrected evidence;
- projected price and FX date propagation;
- stable valuation currency identity after mutable instrument-master correction and fail-closed
  behavior after reporting-currency drift;
- independent portfolio/market observation timestamps and stable value identities;
- fail-closed response behavior when a non-flat current row lacks its local market value;
- service lineage and current-evidence classification;
- recursive OpenAPI documentation; and
- canonical `PB_SG_GLOBAL_BAL_001` route serialization without field loss.

Downstream `lotus-advise#557` must adopt this aggregated Core contract and retain the envelope
through proposal persistence before live memo/report-package acceptance evidence can close.
