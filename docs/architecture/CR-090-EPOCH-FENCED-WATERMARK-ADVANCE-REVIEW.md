# CR-090 Epoch-Fenced Watermark Advance Review

## Scope

- `src/libs/portfolio-common/portfolio_common/position_state_repository.py`
- `src/services/calculators/position_valuation_calculator/app/core/valuation_scheduler.py`
- `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
- `tests/unit/libs/portfolio-common/test_position_state_repository.py`
- `tests/unit/services/calculators/position_valuation_calculator/core/test_valuation_scheduler.py`

## Finding

`PositionStateRepository.bulk_update_states(...)` was updating rows by key only:

- `portfolio_id`
- `security_id`

That meant a scheduler pass could:

1. read a lagging state at epoch `N`
2. calculate a new contiguous watermark for that observed state
3. race with an epoch increment to `N+1`
4. write the older watermark/status onto the newer epoch row

This is a stale-writer bug. It does not create obsolete jobs; it mutates canonical current state
with information derived from an older epoch snapshot.

## Change

- Added `expected_epoch` to bulk state updates
- Fenced `bulk_update_states(...)` on:
  - `portfolio_id`
  - `security_id`
  - `expected_epoch`
- Updated both valuation scheduler implementations to pass the observed epoch through to the
  watermark-advance write
- Added unit coverage proving:
  - stale expected epochs do not overwrite newer rows
  - scheduler-generated updates carry the observed epoch

## Result

Watermark advancement is now aligned with the same epoch-fencing model already applied to:

- control-stage emission
- valuation job creation
- current-epoch candidate selection

An older scheduler pass can no longer overwrite a newer `PositionState` row after the key has
already advanced epochs.

## Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_position_state_repository.py tests/unit/services/calculators/position_valuation_calculator/core/test_valuation_scheduler.py -q`
  - `12 passed`

