# CR-476: Position Calculator Lookup Identifier Normalization

Date: 2026-05-28

## Scope

Position-calculator repository lookup query shape for snapshot fences, position-history replay, and
transaction replay.

## Finding

The position calculator still used raw portfolio/security predicates across several hot-path reads:
latest completed snapshot detection, latest position-history detection, open-security discovery,
transaction replay, last-position lookup, transaction lookup, and stale-position deletion.

Padded caller values or historical padded rows could create false missing-position posture, replay
the wrong transaction window, skip stale-position cleanup, or split an open security into duplicate
partitions. Those failures can distort daily positions before valuation, timeseries generation,
performance, and risk analytics consume the state.

For banking-grade position calculation, repository reads must normalize lookup identifiers while
preserving stored source values and case semantics.

## Change

Updated `PositionRepository` so:

1. repository-local identifier trimming is centralized through `_normalize_identifier(...)`,
2. latest snapshot and latest position-history date reads trim caller and persisted
   portfolio/security IDs,
3. open-security discovery trims the portfolio predicate and partitions by trimmed security ID,
4. transaction replay reads trim caller and persisted portfolio/security IDs,
5. transaction-by-id reads trim transaction ID and optional portfolio ID,
6. stale-position deletion trims caller and persisted portfolio/security IDs.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/position_calculator/repositories/test_position_repository.py -q`
2. `python -m pytest tests/unit/services/calculators/position_calculator -q`
3. `python -m ruff check src/services/calculators/position_calculator/app/repositories/position_repository.py tests/unit/services/calculators/position_calculator/repositories/test_position_repository.py`
4. `python -m ruff format --check src/services/calculators/position_calculator/app/repositories/position_repository.py tests/unit/services/calculators/position_calculator/repositories/test_position_repository.py`
5. `git diff --check`

Results:

1. Focused position repository proof: `5 passed`
2. Position-calculator unit pack: `61 passed`
3. Touched-surface ruff: passed
4. Touched-surface format check: passed
5. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required.
Position-calculator replay and cleanup reads now use trim-normalized identifier lookup semantics at
the repository boundary.
