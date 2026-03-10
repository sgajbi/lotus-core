# CR-089 Current Epoch Valuation Trigger Review

## Scope

- `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`
- `tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py`

## Finding

`find_open_position_keys_for_security_on_date(...)` was selecting any open epoch for a security
as of the target date.

That meant the immediate back-dated price-event path could enqueue valuation work for obsolete
epochs, even when `PositionState` had already advanced the key to a newer current epoch.

The stale-job fence in `ValuationJobRepository` prevented some damage, but the query itself was
still producing semantically wrong work candidates.

## Change

- Tightened `find_open_position_keys_for_security_on_date(...)` to join against
  `PositionState` and return only the current epoch for each `(portfolio_id, security_id)` key
- Added DB-backed integration coverage proving mixed historical epochs resolve to the current
  epoch only

## Result

Immediate valuation triggering from price events now aligns with the canonical key owner:

- historical older epochs remain queryable for audit/history
- active valuation work is scheduled only for the current epoch

## Evidence

- `python -m pytest tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py -k "find_open_position_keys_for_security_on_date_uses_current_epoch_only or stale_older_epoch_job_is_not_rearmed_when_newer_epoch_exists" -q`
  - `2 passed, 5 deselected`
