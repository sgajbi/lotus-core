# CR-467: FX Rate Event Positive Rate Guard

Date: 2026-05-28

## Scope

Shared FX-rate event validation and persistence consumer handling for non-positive FX rates.

## Finding

The FX-rate ingestion DTO already required positive rates, but shared `FxRateEvent` accepted raw
`Decimal` rates without enforcing positivity. Direct Kafka replay, event construction, or
persistence processing could therefore carry a zero or negative FX rate into the authoritative
reference-data store.

For private banking valuation and cost calculation, a non-positive FX rate is not a valid
calculation input. It can corrupt cross-currency market value, cost basis, realized P&L, reporting
currency restatement, and downstream analytics evidence.

## Change

Added shared event-boundary validation so:

1. `FxRateEvent.rate` must be finite and greater than zero,
2. the persistence FX-rate consumer has direct proof that a zero-rate Kafka payload is sent to DLQ
   before idempotency or repository persistence begins,
3. shared event tests now prove non-positive rates fail outside the ingestion API layer.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/repositories/test_persistence_fx_rate_repository.py tests/unit/services/persistence_service/consumers/test_persistence_fx_rate_consumer.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
3. `python -m pytest tests/unit/services/persistence_service -q`
4. `python -m pytest tests/unit/services/calculators/position_valuation_calculator -q`
5. `python -m pytest tests/unit/services/calculators/cost_calculator_service -q`
6. `python -m ruff check src/libs/portfolio-common/portfolio_common/events.py tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/consumers/test_persistence_fx_rate_consumer.py tests/unit/services/persistence_service/repositories/test_persistence_fx_rate_repository.py`
7. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/events.py tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/consumers/test_persistence_fx_rate_consumer.py tests/unit/services/persistence_service/repositories/test_persistence_fx_rate_repository.py`
8. `git diff --check`

Results:

1. Focused FX-rate proof: `19 passed`
2. Portfolio-common unit pack: `486 passed`
3. Persistence-service unit pack: `18 passed`
4. Position valuation calculator unit pack: `31 passed`
5. Cost calculator unit pack: `104 passed`
6. Touched-surface ruff: passed
7. Touched-surface format check: passed
8. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. FX-rate
event boundaries now fail closed for non-positive cross-currency reference rates before persistence
or downstream valuation/cost lookup can consume them.
