# CR-151 - Position State Hot Path Index Review

## Scope
- `position_state`
- valuation scheduler lagging-state scans
- terminal `REPROCESSING -> CURRENT` normalization
- replay watermark update paths

## Finding
`PositionState` is the canonical replay and valuation control row, but its hottest scheduler-facing scans still relied on a single-column status index and primary-key lookups.

That leaves avoidable scan and sort pressure on:
- lagging state discovery ordered by `updated_at`
- terminal `REPROCESSING` normalization
- watermark lag scans keyed by `watermark_date`

## Fix
- Add composite indexes aligned to the live query patterns:
  - `(status, watermark_date, updated_at)`
  - `(watermark_date, updated_at)`

## Result
The core replay/valuation control table now has index support aligned to its actual lagging and terminal-state scheduler access patterns.
