# CR-1121 Cost Basis Strategy Consumption Boundary

Date: 2026-06-21

## Scope

Cost calculator engine cost-basis strategy logic in
`src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_basis_strategies.py`.

## Finding

The FIFO and AVCO cost-basis strategy module was A-ranked for maintainability, but two domain
helpers still concentrated validation and lot-consumption policy:

- `_validated_buy_lot_inputs`: `B (9)`
- `FIFOBasisStrategy.consume_sell_quantity`: `B (7)`

These paths are calculation-critical because they determine whether dirty BUY lots are rejected,
whether zero-quantity/zero-cost seed artifacts are ignored, how FIFO lots are mutated, and how base
and local COGS are calculated for SELL transactions.

## Action Taken

Split the cost-basis policy into focused helpers for:

- required BUY cost-basis field presence,
- one-pass decimal normalization of lot inputs,
- empty zero-quantity/zero-cost lot skipping,
- positive quantity and non-negative cost-basis validation,
- single FIFO lot consumption and remaining-lot quantity mutation.

The public strategy protocol, FIFO/AVCO strategy classes, error messages, COGS arithmetic, and
open-lot quantity output remain unchanged.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\calculators\cost_calculator_service\engine\test_cost_basis_strategies.py tests\unit\services\calculators\cost_calculator_service\engine\test_cost_basis_property_invariants.py -q`
- Result: `20 passed`

Broader cost-engine proof:

- `python -m pytest tests\unit\services\calculators\cost_calculator_service\engine -q`
- Result: `91 passed`

Broader cost-calculator service proof:

- `python -m pytest tests\unit\services\calculators\cost_calculator_service -q`
- Result: `133 passed`

Focused static proof:

- `python -m ruff check src\services\calculators\cost_calculator_service\app\cost_engine\processing\cost_basis_strategies.py tests\unit\services\calculators\cost_calculator_service\engine\test_cost_basis_strategies.py tests\unit\services\calculators\cost_calculator_service\engine\test_cost_basis_property_invariants.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src\services\calculators\cost_calculator_service\app\cost_engine\processing\cost_basis_strategies.py -s --min B`
- Result: no B-or-worse functions/classes reported

Measured movement:

- `_validated_buy_lot_inputs`: `B (9)` -> no longer B-ranked
- `FIFOBasisStrategy.consume_sell_quantity`: `B (7)` -> no longer B-ranked
- `cost_basis_strategies.py` maintainability remains A-ranked (`A (37.00)`)

## Residual Risk

This slice does not change API contracts or cross-app integrations. The remaining cost-engine
modularity backlog is broader than this module: `cost_calculator.py` still reports B-ranked
maintainability because it remains a large calculation module, even after CR-1120 removed its
B/C-ranked functions.

## Bank-Buyable Control Movement

This slice improves:

- deterministic cost-basis calculation reviewability,
- calculation-domain validation boundaries,
- behavior-preserving refactor evidence for FIFO and AVCO cost-basis logic.

It does not claim full bank-buyable readiness for `lotus-core`.
