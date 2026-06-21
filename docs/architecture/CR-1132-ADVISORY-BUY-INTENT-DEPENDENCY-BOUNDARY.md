# CR-1132 Advisory Buy Intent Dependency Boundary

Date: 2026-06-21

## Scope

Query-service advisory simulation BUY intent dependency linking in
`src/services/query_service/app/advisory_simulation/common/intent_dependencies.py`.

## Finding

`link_buy_intent_dependencies(...)` attached FX funding and optional same-currency SELL dependencies
to BUY security intents. The behavior was deterministic, but the function mixed security-intent
filtering, notional currency extraction, sell-dependency indexing, duplicate suppression, and
dependency mutation in one C-ranked helper.

Radon reported:

- `link_buy_intent_dependencies`: `C (16)`

## Action Taken

Extracted focused helpers for:

- security-trade side detection with type narrowing,
- notional currency extraction,
- same-currency SELL dependency indexing,
- BUY security intent filtering,
- append-once dependency mutation,
- per-BUY dependency linking.

Added focused regression coverage proving FX intents are ignored as mutation targets and
same-currency SELL dependencies are not attached when the option is disabled.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\advisory_simulation\test_simulation_helpers.py -q`
- Result: `3 passed`

Focused static proof:

- `python -m ruff check src\services\query_service\app\advisory_simulation\common\intent_dependencies.py tests\unit\services\query_service\advisory_simulation\test_simulation_helpers.py`
- Result: passed

Focused type proof:

- `make typecheck`
- Result: passed

Focused complexity proof:

- `python -m radon cc src\services\query_service\app\advisory_simulation\common\intent_dependencies.py -s`
- Result: `link_buy_intent_dependencies` is `A (3)`, and all functions in
  `intent_dependencies.py` are A-ranked.

Focused maintainability proof:

- `python -m radon mi src\services\query_service\app\advisory_simulation\common\intent_dependencies.py -s`
- Result: `A (49.97)`

Measured movement:

- `link_buy_intent_dependencies`: `C (16)` -> `A (3)`
- `intent_dependencies.py` function-level complexity: no B-or-worse functions remain

## Residual Risk

This slice does not change API contracts, OpenAPI, advisory simulation response shape, or dependency
semantics. Larger advisory simulation hotspots remain in compliance and funding logic.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of advisory intent execution ordering,
- type-safe separation of security and FX intent handling,
- focused regression evidence for deterministic dependency mutation.

It does not claim full bank-buyable readiness for `lotus-core`.
