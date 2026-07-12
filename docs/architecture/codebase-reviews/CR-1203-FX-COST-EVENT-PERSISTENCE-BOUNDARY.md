# CR-1203: FX Cost Event Persistence Boundary

## Objective

Prevent governed event-envelope fields from leaking into transaction-table upserts during FX cost
processing.

## Defect Evidence

PR Merge Gate E2E smoke logs for head `210d6c18` showed FX lifecycle transactions going to the DLQ
from `cost_calculator_service` with `AttributeError: event_type`. The cost calculator persisted FX
processed `TransactionEvent` payloads directly into the `transactions` table upsert. Once governed
event envelope fields such as `event_type` were present, SQLAlchemy could not build
`stmt.excluded.event_type` because `event_type` is not a `transactions` column.

The downstream symptom was empty FX contract and cash position history because cost processed
events were not emitted, so pipeline readiness and position calculation never ran for those rows.

## Decision

Use a persistence-boundary payload helper in the cost repository:

- Strip governed event envelope fields with `event_business_payload(...)`.
- Persist only fields that exist on the `transactions` SQLAlchemy model.
- Keep fee-component and epoch exclusions explicit because those are processing/runtime fields, not
  transaction-table columns.

This is intentionally broader than excluding only `event_type`; future envelope additions should
not be able to break the FX cost path in the same way.

## Expected Improvement

- FX spot, forward, and swap lifecycle rows can persist processed transaction metadata without DLQ
  failures caused by non-persistence event fields.
- The repository boundary now enforces DTO/event-to-persistence anti-corruption instead of relying
  on every caller to send a table-shaped object.
- The same class of schema-envelope drift becomes covered by a focused regression test.

## Validation Evidence

- `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -q`
  => 40 passed.
- `python -m ruff check src/services/calculators/cost_calculator_service/app/repository.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py`
  => passed.
- `make quality-wiki-docs-gate` => passed.
- `git diff --check` => passed.

## Downstream Compatibility

No API, Kafka topic, database schema, route, or response-shape change. The fix preserves intended
FX lifecycle behavior by allowing already-valid processed transaction events to reach the existing
cost, readiness, and position pipelines.
