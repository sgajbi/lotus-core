# CR-393: Cost Consumer Upstream Cash-Leg Type Normalization

Date: 2026-05-28

## Scope

Cost calculator consumer upstream-provided cash-leg validation.

## Finding

The cost consumer normalized the incoming event transaction type for top-level routing, but the
later upstream-provided cash-leg validation compared `processed_event.transaction_type.upper()`
directly against `ADJUSTMENT`. A padded lower-case cash-leg row such as ` adjustment ` could be
misclassified as a product leg and incorrectly forced to carry `external_cash_transaction_id`,
sending an otherwise valid upstream cash leg toward the generic failure/DLQ path.

## Change

Reused the consumer's existing event-code normalizer for the upstream cash-leg product-leg check.
Added direct consumer coverage proving a padded lower-case upstream `ADJUSTMENT` cash leg publishes
without fetching transaction history, without requiring an external cash id, and without DLQ.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -q`
2. `python -m pytest tests/unit/services/calculators/cost_calculator_service -q`
3. `python -m ruff check src/services/calculators/cost_calculator_service/app/consumer.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a cost-consumer
cash-leg routing and replay-correctness slice.
