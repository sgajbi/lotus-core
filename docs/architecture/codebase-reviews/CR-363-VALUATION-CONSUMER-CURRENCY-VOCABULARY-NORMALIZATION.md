# CR-363 Valuation Consumer Currency Vocabulary Normalization

Date: 2026-05-27

## Scope

Reviewed position valuation consumer currency handling after valuation logic FX guardrails were
hardened.

## Findings

`ValuationLogic.calculate_valuation(...)` normalizes currency codes before FX requirement checks,
but `ValuationConsumer` still decided whether an FX rate was required using raw
`instrument.currency` and `portfolio.base_currency` values.

That created a pre-calculation failure path: padded or lower-case same-currency values such as
`" usd "` and `" USD "` could be treated as cross-currency before valuation logic ran. If no FX row
was available, the job could be marked `FAILED` for missing FX even though the valuation was
same-currency and should have used FX `1`.

## Actions Taken

Hardened
`src/services/calculators/position_valuation_calculator/app/consumers/valuation_consumer.py`:

1. added a consumer-local currency normalizer using `strip().upper()`,
2. normalized instrument, portfolio, and price currencies before valuation,
3. skipped FX lookup for normalized same-currency valuations,
4. used normalized currency codes in missing-FX failure messages and valuation logic calls.

Added direct async unit proof that padded same-currency instrument, portfolio, and price currencies
avoid FX lookup and still produce a valued snapshot.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/calculators/position_valuation_calculator/consumers/test_valuation_consumer.py -q
7 passed

python -m pytest tests/unit/services/calculators/position_valuation_calculator -q
30 passed

python -m ruff check src/services/calculators/position_valuation_calculator/app/consumers/valuation_consumer.py tests/unit/services/calculators/position_valuation_calculator/consumers/test_valuation_consumer.py
All checks passed
```

## Follow-Up

No API or wiki source change is required because this hardens internal valuation job processing
without changing public contracts. Continue reviewing valuation repository lookup inputs for
currency-code normalization and index-friendly FX lookup behavior.
