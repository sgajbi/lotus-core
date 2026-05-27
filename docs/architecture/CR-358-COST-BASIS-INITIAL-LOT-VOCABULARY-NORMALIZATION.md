# CR-358 Cost Basis Initial Lot Vocabulary Normalization

Date: 2026-05-27

## Scope

Reviewed cost-basis state initialization for historical lot replay after cost-engine execution and
strategy routing normalization.

## Findings

Both `FIFOBasisStrategy.set_initial_lots(...)` and
`AverageCostBasisStrategy.set_initial_lots(...)` seeded initial lots only when
`transaction_type == "BUY"`.

Historical transactions loaded from persistence or replay may carry padded or lower-case source
vocabulary even after newer calculator execution paths normalize fresh events. If those historical
BUY rows are skipped during state initialization, downstream SELL, transfer-out, cash-in-lieu, and
corporate-action disposal calculations can see zero or understated available holdings.

## Actions Taken

Hardened `src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_basis_strategies.py`:

1. added a shared `_is_buy_transaction(...)` helper using `strip().upper()`,
2. applied it to FIFO initial-lot seeding,
3. applied it to average-cost initial-lot seeding.

Added direct unit proof for:

1. FIFO seeding of a padded lower-case historical BUY transaction,
2. average-cost seeding of a padded lower-case historical BUY transaction.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/calculators/cost_calculator_service/engine/test_cost_basis_strategies.py -q
10 passed

python -m pytest tests/unit/services/calculators/cost_calculator_service -q
94 passed

python -m ruff check src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_basis_strategies.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_basis_strategies.py
All checks passed
```

## Follow-Up

No API or wiki source change is required because this improves internal cost-basis replay behavior
without changing public contracts. Continue reviewing persisted historical transaction loading and
reprocessing consumers so replayed calculation state uses canonical vocabulary consistently.
