# CR-093 Position State Mutation Timestamp Integrity Review

## Scope

- `src/libs/portfolio-common/portfolio_common/position_state_repository.py`
- `tests/unit/libs/portfolio-common/test_position_state_repository.py`

## Finding

`PositionState` is the canonical current-state table for replay and watermark control, but its two
replay-critical mutation paths did not explicitly refresh `updated_at`:

- `increment_epoch_and_reset_watermark(...)`
- `update_watermarks_if_older(...)`

That left timestamp integrity dependent on ORM-level `onupdate` behavior instead of explicit write
intent in the SQL mutation itself.

## Change

- Added `updated_at=func.now()` to both state-mutation statements
- Added DB-backed assertions that the mutated rows retain a populated `updated_at`

## Result

`PositionState.updated_at` now correctly tracks replay/watermark mutations at the database write
layer instead of relying on implicit behavior.

## Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_position_state_repository.py -q`
