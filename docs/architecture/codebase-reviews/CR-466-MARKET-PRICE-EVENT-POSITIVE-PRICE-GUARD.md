# CR-466: Market Price Event Positive Price Guard

Date: 2026-05-28

## Scope

Shared market-price event validation and persistence consumer handling for non-positive market
prices.

## Finding

The market-price ingestion DTO already required positive prices, but shared `MarketPriceEvent` and
`MarketPricePersistedEvent` accepted raw `Decimal` prices without enforcing positivity. Direct
event construction, replay payloads, or persistence/outbox reconstruction could therefore carry a
zero or negative market price into valuation and reprocessing flows.

For private banking valuation, a non-positive market price is not a recoverable calculation input;
it can materially distort market value, P&L, supportability evidence, and downstream analytics.

## Change

Added shared event-boundary validation so:

1. `MarketPriceEvent.price` must be finite and greater than zero,
2. `MarketPricePersistedEvent.price` must be finite and greater than zero,
3. persistence market-price consumer coverage proves a zero-price Kafka payload is sent to DLQ
   before idempotency, repository persistence, or outbox publication begins.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/consumers/test_persistence_market_price_consumer.py tests/unit/services/persistence_service/repositories/test_market_price_repository.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
3. `python -m pytest tests/unit/services/persistence_service -q`
4. `python -m pytest tests/unit/services/valuation_orchestrator_service/consumers/test_price_event_consumer.py tests/unit/services/calculators/position_valuation_calculator/consumers/test_valuation_consumer.py -q`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/events.py tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/consumers/test_persistence_market_price_consumer.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/events.py tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/consumers/test_persistence_market_price_consumer.py`
7. `git diff --check`

Results:

1. Focused market-price proof: `18 passed`
2. Portfolio-common unit pack: `484 passed`
3. Persistence-service unit pack: `16 passed`
4. Valuation/price consumer proof: `15 passed`
5. Touched-surface ruff: passed
6. Touched-surface format check: passed
7. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. Market
price event boundaries now fail closed for non-positive valuation prices before persistence or
downstream valuation orchestration.
