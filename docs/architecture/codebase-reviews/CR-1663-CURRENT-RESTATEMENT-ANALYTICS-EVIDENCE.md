# CR-1663 Current Restatement Analytics Evidence

## Objective

Make the analytics-input currentness contract deterministic when an authoritative position
timeline converges through a positive recovery epoch.

## Finding

An isolated `timeseries_contracts` rerun passed, while a prior run of the same source produced the
same economics at epoch one and timed out waiting for portfolio status `final`. The interleaving is
legal: valuation can complete a later business date between two ordered earlier-date cash events,
after which the later event correctly advances the position recovery epoch and rebuilds the
timeline.

Query Control Plane selected only rows matching `PositionState.epoch`, but then classified every
`restated` row as stale. The response therefore exposed an authoritative current restatement as
`data_quality_status=STALE`, `source_evidence_current=false`, and `freshness_status=STALE`.
This conflated calculation lineage with source freshness and made E2E completion depend on
scheduler timing.

## Correction

- Preserve `valuation_status=restated` for positive epochs.
- Treat `final` and `restated` as current valuation states; unknown, provisional, or explicit stale
  states remain stale.
- Derive source currentness from complete requested-window coverage after the repository's exact
  current-epoch fence.
- Keep missing dates and pagination incomplete, and retain the complete quality-status
  distribution so consumers can distinguish original from restated values.
- Make E2E acceptance require exact economics plus current evidence while accepting either legal
  epoch lineage.

## Compatibility

Route paths, request/response fields, event schemas, database schemas, Kafka topology, partition
counts, formulas, and timeout budgets are unchanged. The intentional behavior correction is that a
complete authoritative restatement now reports `COMPLETE` / current rather than `STALE`.
OpenAPI descriptions now state that `stale_points_count` excludes authoritative restatements.
Downstream consumers still receive `valuation_status=restated` and the quality distribution.

## Evidence

- Exact-source pre-change isolated E2E: `4 passed in 393.62s`.
- Focused analytics unit proof after correction: `86 passed in 2.21s`.
- Final lint, OpenAPI, E2E, protected CI, and exact-main evidence are recorded on issue #490.

