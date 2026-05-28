# CR-463: Transaction Event Temporal Ordering Guard

Date: 2026-05-28

## Scope

Shared `TransactionEvent` temporal normalization and deterministic ordering for transaction
replay, position recalculation, and calculator event processing.

## Finding

`TransactionEvent` accepted naive datetimes for `transaction_date`, `settlement_date`, and
`created_at`. The shared `transaction_event_ordering_key(...)` also used an aware UTC fallback for
missing `created_at`, which meant mixed naive and aware event timestamps could fail during sorting.

That is a direct replay-reliability risk. Backdated position recalculation sorts historical
transactions and the triggering event together; if one path supplies an aware timestamp while
another supplies a naive timestamp, deterministic replay can fail before calculation begins.

## Change

Added shared event temporal normalization:

1. `TransactionEvent` constructor validation now treats naive `transaction_date`,
   `settlement_date`, and `created_at` as UTC-aware timestamps,
2. ISO strings ending in `Z` are parsed as UTC-aware timestamps at the shared event boundary,
3. `transaction_event_ordering_key(...)` now normalizes the transaction and ingestion timestamps
   used for ordering, so replay sorting remains safe even if a caller mutates an event after model
   construction.

The change preserves the existing event contract shape and does not add route, database, or
OpenAPI changes.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_events.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py::test_calculate_backdated_replay_has_deterministic_tie_break_order -q`
2. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
3. `python -m pytest tests/unit/services/calculators/position_calculator -q`
4. `python -m pytest tests/unit/services/calculators/cost_calculator_service -q`
5. `python -m pytest tests/unit/services/persistence_service -q`
6. `python -m ruff check src/libs/portfolio-common/portfolio_common/events.py tests/unit/libs/portfolio-common/test_events.py`
7. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/events.py tests/unit/libs/portfolio-common/test_events.py`
8. `git diff --check`

Results:

1. Focused temporal replay proof: `9 passed`
2. Portfolio-common unit pack: `482 passed`
3. Position-calculator unit pack: `56 passed`
4. Cost-calculator unit pack: `102 passed`
5. Persistence-service unit pack: `15 passed`
6. Touched-surface ruff: passed
7. Touched-surface format check: passed
8. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
shared transaction event boundary and ordering helper now protect calculator replay paths from
mixed naive/aware timestamp failures.
