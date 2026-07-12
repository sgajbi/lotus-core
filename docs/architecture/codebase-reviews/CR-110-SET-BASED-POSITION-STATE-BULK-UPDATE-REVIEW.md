# CR-110 Set-Based Position State Bulk Update Review

## Scope

- `src/libs/portfolio-common/portfolio_common/position_state_repository.py`
- `tests/unit/libs/portfolio-common/test_position_state_repository.py`

## Finding

`PositionStateRepository.bulk_update_states(...)` was functionally correct, but it
executed one `UPDATE` statement per row.

That is acceptable at small scale, but it is not the right shape for a hot
control table used by:

- valuation watermark advancement
- terminal reprocessing normalization
- any future replay/state bulk transition path

Because the method is already epoch-fenced by `(portfolio_id, security_id,
expected_epoch)`, it is a good candidate for a single set-based update using a
derived values table.

## Action Taken

- Replaced the row-by-row loop with a single PostgreSQL set-based `UPDATE ...
  FROM (VALUES ...)` style statement
- Preserved the same epoch fence and `updated_at = now()` mutation semantics
- Added test coverage for multi-row `updated_at` integrity

## Result

The scheduler and replay control plane now mutate `position_state` in one
database round-trip per prepared batch, instead of one round-trip per row,
without weakening the epoch fence.
