# CR-1122 Cost Engine Dependency Sorter Boundary

Date: 2026-06-21

## Scope

Cost calculator engine transaction dependency sorting in
`src/services/calculators/cost_calculator_service/app/cost_engine/processing/sorter.py`.

## Finding

The cost-engine sorter was A-ranked for maintainability, but the dependency rank policy still used
branch-heavy helpers in a calculation-critical ordering path:

- `_cash_dependency_rank`: `B (10)`
- `_ca_bundle_a_dependency_rank`: `B (8)`

These helpers determine deterministic same-timestamp processing order for Bundle A, rights
lifecycle, and cash-settlement events before `TransactionProcessor` calculates cost basis and
publishes downstream calculator effects.

## Action Taken

Moved the dependency policy into named rank maps and focused cash predicates for:

- Bundle A and rights transaction dependency ranks,
- cash transaction detection,
- cash inflow component and transaction type classification,
- cash outflow component and transaction type classification.

The public sorter contract, sort-key order, transaction model shape, and downstream processor
orchestration remain unchanged.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\calculators\cost_calculator_service\engine\test_sorter.py -q`
- Result: `8 passed`

Focused static proof:

- `python -m ruff check src\services\calculators\cost_calculator_service\app\cost_engine\processing\sorter.py tests\unit\services\calculators\cost_calculator_service\engine\test_sorter.py`
- Result: passed after Ruff import normalization

Focused complexity proof:

- `python -m radon cc src\services\calculators\cost_calculator_service\app\cost_engine\processing\sorter.py -s --min B`
- Result: no B-or-worse functions/classes reported

Focused maintainability proof:

- `python -m radon mi src\services\calculators\cost_calculator_service\app\cost_engine\processing\sorter.py -s`
- Result: `A (66.03)`

Measured movement:

- `_cash_dependency_rank`: `B (10)` -> no longer B-ranked
- `_ca_bundle_a_dependency_rank`: `B (8)` -> no longer B-ranked
- `sorter.py` maintainability remains A-ranked and improves from `A (63.50)` to `A (66.03)`

## Residual Risk

This slice does not change API contracts, persistence, or cross-app integration contracts. It
preserves internal ordering behavior and adds direct component-type settlement ordering proof. The
remaining calculator backlog still includes repository persistence methods, reprocessing consumer
orchestration, transaction datetime normalization, and larger position-calculator hotspots.

## Bank-Buyable Control Movement

This slice improves:

- deterministic calculation-order policy reviewability,
- explicit dependency vocabulary for Bundle A, rights, and cash settlement ordering,
- focused regression evidence for a real calculation precondition.

It does not claim full bank-buyable readiness for `lotus-core`.
