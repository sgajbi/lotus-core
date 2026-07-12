# CR-088 Stale Valuation Epoch Job Review

## Scope

- `src/libs/portfolio-common/portfolio_common/valuation_job_repository.py`
- `tests/unit/libs/portfolio-common/test_valuation_job_repository.py`
- `tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py`

## Finding

`PortfolioDayReadyForValuation` events carry an epoch, but `ValuationJobRepository.upsert_job(...)`
previously accepted any epoch for a given `(portfolio_id, security_id, valuation_date)` scope.

That meant an older readiness event could still create or re-arm stale valuation work after a
newer epoch already existed for the same portfolio-security-date.

## Change

- Added `get_latest_epoch_for_scope(...)` to `ValuationJobRepository`
- Hardened `upsert_job(...)` so it skips older-epoch upserts when a newer epoch already exists
  for the same scope
- Added:
  - unit coverage proving stale older-epoch upserts are skipped
  - DB-backed integration coverage proving an older epoch does not create a second stale job row

## Result

Valuation job scheduling is now monotonic across epochs for a fixed
`(portfolio_id, security_id, valuation_date)` scope:

- current epoch work is preserved
- stale older-epoch readiness cannot reintroduce obsolete valuation jobs

## Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_valuation_job_repository.py -q`
  - `2 passed`
- `python -m pytest tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py -k stale_older_epoch_job_is_not_rearmed_when_newer_epoch_exists -q`
  - `1 passed`
