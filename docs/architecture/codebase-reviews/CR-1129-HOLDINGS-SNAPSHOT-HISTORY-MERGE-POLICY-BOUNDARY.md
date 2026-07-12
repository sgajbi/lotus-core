# CR-1129 Holdings Snapshot-History Merge Policy Boundary

Date: 2026-06-21

## Scope

Query-service HoldingsAsOf snapshot/history merge policy in
`src/services/query_service/app/services/position_holdings.py`.

## Finding

`merge_snapshot_and_history_position_rows(...)` owned the source-row precedence policy for
`HoldingsAsOf:v1`: normalized security identity, snapshot authority, history-only inclusion, and
history substitution when snapshot booked basis no longer matched current position history. The
behavior was tested, but the function still mixed indexing, snapshot split, mismatch detection,
history-only supplementation, and merged output assembly in one B-ranked helper.

Radon reported:

- `merge_snapshot_and_history_position_rows`: `B (7)`

## Action Taken

Extracted focused helpers for:

- typed position row result identity,
- normalized position-result indexing,
- snapshot/history booked-basis mismatch detection,
- snapshot-result versus history-supplement splitting,
- history-only supplementation.

The public merge helper signature, snapshot-authority behavior, history-only behavior,
basis-mismatch substitution, normalized security IDs, and returned tuple shape remain unchanged.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_holdings_response.py -q`
- Result: `34 passed`

Focused static proof:

- `python -m ruff check src\services\query_service\app\services\position_holdings.py tests\unit\services\query_service\services\test_position_holdings.py tests\unit\services\query_service\services\test_position_holdings_response.py`
- Result: passed

Focused type proof:

- `make typecheck`
- Result: passed

Focused complexity proof:

- `python -m radon cc src\services\query_service\app\services\position_holdings.py -s`
- Result: `merge_snapshot_and_history_position_rows` is `A (1)`, and all functions in
  `position_holdings.py` are A-ranked.

Focused maintainability proof:

- `python -m radon mi src\services\query_service\app\services\position_holdings.py -s`
- Result: `A (25.48)`

Measured movement:

- `merge_snapshot_and_history_position_rows`: `B (7)` -> `A (1)`
- `position_holdings.py` function-level complexity: no B-or-worse functions remain
- `position_holdings.py` maintainability remains A-ranked at `A (25.48)`

## Residual Risk

This slice does not change API contracts, OpenAPI, persistence, or cross-app integration behavior.
The next HoldingsAsOf refactor target should be chosen from broader service/repository evidence
rather than continuing to split already A-ranked helpers in `position_holdings.py`.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of source-row precedence for HoldingsAsOf evidence,
- explicit booked-basis mismatch policy for stale snapshot substitution,
- confidence that snapshot/history merge behavior remains covered by focused tests.

It does not claim full bank-buyable readiness for `lotus-core`.
