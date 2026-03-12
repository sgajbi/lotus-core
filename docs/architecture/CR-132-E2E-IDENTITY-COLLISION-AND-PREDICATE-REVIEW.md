# CR-132 E2E Identity Collision and Predicate Review

## Finding
Two broad-suite E2E failures were caused by test-contract defects rather than runtime regressions:

1. `test_fx_lifecycle_cash_positions_reflect_settlement_pairs` used `set(by_security) < required`, which is a strict-subset test, not a containment check. Extra positions could therefore bypass the missing-key guard and raise `KeyError`.
2. `test_timeseries_pipeline` reused static portfolio, instrument, cash, and transaction identifiers. Under the full suite, that made the scenario vulnerable to cross-module identity collision and stale read contamination.

## Change
- Fixed the FX cash-position predicate to use `required.issubset(set(by_security))`.
- Randomized the timeseries scenario identifiers with a per-module UUID suffix.

## Why This Is Correct
E2E failures must represent pipeline defects, not weak fixture identity or invalid predicate logic. Unique seeded identities and correct containment checks make the tests deterministic and meaningful.

## Evidence
- `python -m pytest tests/e2e/test_fx_lifecycle.py -x -q`
- `python -m pytest tests/e2e/test_timeseries_pipeline.py -x -q`
- `python -m pytest tests/e2e -x -q`
