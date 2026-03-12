# CR-139 Position Epoch Bump Fence Review

## Scope
- `PositionStateRepository.increment_epoch_and_reset_watermark(...)`
- back-dated replay path in `PositionCalculator.calculate(...)`

## Finding
The position replay epoch-bump path incremented `PositionState.epoch` by key only, with no expected-epoch fence.

That meant two concurrent workers handling the same back-dated original event class could both increment the same key and both publish replay, even though only one worker should win the epoch transition.

## Fix
- Added an explicit `expected_epoch` fence to `increment_epoch_and_reset_watermark(...)`.
- The repository now returns `None` when the caller loses the epoch race.
- `PositionCalculator.calculate(...)` now treats that stale loser as terminal for the current attempt and does not stage replay outbox events.

## Validation
- `python -m pytest tests/unit/libs/portfolio-common/test_position_state_repository.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/position_state_repository.py src/services/calculators/position_calculator/app/core/position_logic.py tests/unit/libs/portfolio-common/test_position_state_repository.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py`

## Status
- Hardened
