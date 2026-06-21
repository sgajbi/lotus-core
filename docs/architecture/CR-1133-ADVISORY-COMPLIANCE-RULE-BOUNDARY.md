# CR-1133 Advisory Compliance Rule Boundary

Date: 2026-06-21

## Scope

Query-service advisory simulation compliance rule evaluation in
`src/services/query_service/app/advisory_simulation/compliance.py`.

## Finding

`RuleEngine.evaluate(...)` assembled all advisory post-trade rule results in one branch-heavy
method. The behavior was deterministic, but the method mixed cash-band evaluation, single-position
limit evaluation, data-quality counting, suppressed-intent reporting, shorting checks, and
negative-cash checks in one C-ranked boundary.

Radon reported:

- `RuleEngine`: `C (20)`
- `RuleEngine.evaluate`: `C (19)`

## Action Taken

Extracted focused helpers for:

- common `RuleResult` construction,
- cash-weight lookup and cash-band evaluation,
- single-position no-limit, pass, and breach result construction,
- data-quality issue counting,
- suppressed-intent reporting,
- negative-position detection,
- negative-cash detection.

Added direct regression coverage proving multiple single-position limit breaches continue to emit
multiple `SINGLE_POSITION_MAX` failure rows instead of collapsing into one finding.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\advisory_simulation\test_compliance.py -q`
- Result: `6 passed`

Focused static proof:

- `python -m ruff check src\services\query_service\app\advisory_simulation\compliance.py tests\unit\services\query_service\advisory_simulation\test_compliance.py`
- Result: passed

Focused type proof:

- `make typecheck`
- Result: passed

Focused complexity proof:

- `python -m radon cc src\services\query_service\app\advisory_simulation\compliance.py -s`
- Result: `RuleEngine` is `A (2)`, `RuleEngine.evaluate` is `A (1)`, and all functions in
  `compliance.py` are A-ranked.

Focused maintainability proof:

- `python -m radon mi src\services\query_service\app\advisory_simulation\compliance.py -s`
- Result: `A (51.42)`

Measured movement:

- `RuleEngine`: `C (20)` -> `A (2)`
- `RuleEngine.evaluate`: `C (19)` -> `A (1)`
- `compliance.py` function-level complexity: no B-or-worse functions remain

## Residual Risk

This slice does not change API contracts, OpenAPI, advisory simulation response shape, or rule
semantics. CR-1134 addresses the measured advisory funding hotspot on the same branch.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of post-trade compliance rule evaluation,
- deterministic audit evidence for multi-breach single-position limits,
- isolation of hard-rule and soft-rule result construction.

It does not claim full bank-buyable readiness for `lotus-core`.
