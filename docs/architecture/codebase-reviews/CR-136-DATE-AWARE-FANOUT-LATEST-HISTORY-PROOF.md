## CR-136 - Date-Aware Fanout Latest-History Proof

### Finding
The worker replay fanout had already been corrected to use `find_portfolios_holding_security_on_date(...)`, but the lower-level proof still focused only on obvious pre-impact closures and future opens. It did not prove the subtler contract that matters in practice: the lookup must use the latest history row on or before the impacted date, not any older positive row.

### Fix
- Added a DB-backed integration proof where the same portfolio:
  - holds a security,
  - closes it before the impacted date,
  - and reopens it after the impacted date.
- The repository now has an explicit test proving:
  - no replay fanout at the impacted date
  - replay fanout resumes after the reopen date

### Why it matters
This is the real business contract behind date-aware replay fanout. Without the proof, a future refactor could regress to “any historical holding” semantics and reintroduce unnecessary replay pressure.

### Evidence
- `tests/integration/services/calculators/position_valuation_calculator/test_int_instrument_reprocessing_repo.py`
