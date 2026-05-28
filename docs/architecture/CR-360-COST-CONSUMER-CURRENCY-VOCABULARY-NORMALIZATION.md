# CR-360 Cost Consumer Currency Vocabulary Normalization

Date: 2026-05-27

## Scope

Reviewed cost-calculator consumer normalization before transaction events enter the cost engine.

## Findings

The cost engine now defensively normalizes transaction type, policy, cash-instrument, sorting, and
initial-lot replay values, but the consumer still had raw source-code comparisons in front of the
engine:

1. lifecycle metric classification uppercased transaction types without trimming,
2. FX enrichment compared raw `trade_currency` to portfolio base currency,
3. event dispatch and retry/failure metric classification uppercased transaction type without
   trimming.

The FX enrichment issue was calculation-affecting: a same-currency transaction with padded or
lower-case currency values could be treated as cross-currency and deferred for a missing FX rate
instead of reaching same-currency calculation with FX `1`.

## Actions Taken

Hardened `src/services/calculators/cost_calculator_service/app/consumer.py`:

1. added one consumer-local `strip().upper()` code normalizer,
2. applied it to lifecycle metric classification,
3. normalized trade and portfolio currencies before FX lookup decisions,
4. normalized event transaction type before dispatch,
5. normalized exception-path SELL metric classification,
6. cleaned touched-file Ruff import ordering and long-line debt.

Added direct async unit proof that padded same-currency `trade_currency` and portfolio base currency
avoid unnecessary FX lookup and are passed forward as canonical `USD`.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -q
20 passed

python -m pytest tests/unit/services/calculators/cost_calculator_service -q
98 passed

python -m ruff check src/services/calculators/cost_calculator_service/app/consumer.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py
All checks passed
```

## Follow-Up

No API or wiki source change is required because this hardens consumer-side normalization without
changing public contracts. Continue reviewing repository persistence and reprocessing paths for
remaining raw source-code comparisons that can affect replay, idempotency, or calculation routing.
