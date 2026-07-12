# CR-127 Typed Instrument Trigger Upsert Review

## Finding

`InstrumentReprocessingStateRepository.upsert_state(...)` was already atomic, but it
still built the impacted-date merge logic with string SQL:

- `LEAST(instrument_reprocessing_state.earliest_impacted_date, 'YYYY-MM-DD')`

That was weaker than the replay job queue path we just hardened:

- it embedded request data into a raw SQL string
- it made the write contract less explicit in code review
- it created an avoidable divergence between two adjacent replay-trigger boundaries

## Change

Replaced the raw `text(...)` expression with a typed SQLAlchemy expression:

- `func.least(InstrumentReprocessingState.earliest_impacted_date, stmt.excluded.earliest_impacted_date)`
- explicit `updated_at = func.now()`

This preserves the same atomic PostgreSQL upsert semantics while keeping the
repository contract typed and structurally consistent with the rest of the
replay hardening work.

## Why It Matters

This is not a cosmetic style fix. The instrument trigger table is the durable
source of replay intent for back-dated price events. The queue path and the
trigger-source path should both use explicit, typed, atomic merge logic rather
than mixing typed upserts with hand-built SQL fragments.

## Evidence

- `src/services/valuation_orchestrator_service/app/repositories/instrument_reprocessing_state_repository.py`
- `tests/integration/services/valuation_orchestrator_service/test_instrument_reprocessing_state_repository.py`
