# CR-1163 Cost Reprocessing Consumer Boundary

Date: 2026-06-30

## Scope

- `src/services/calculators/cost_calculator_service/app/consumers/reprocessing_consumer.py`
- `tests/unit/services/calculators/cost_calculator_service/consumer/test_reprocessing_consumer.py`

## Finding

`ReprocessingConsumer.process_message(...)` mixed Kafka payload parsing, fallback correlation
selection, transaction-id validation, Kafka producer creation, DB session iteration, repository
construction, retryable database error handling, malformed-payload DLQ behavior, and unexpected
error DLQ behavior in one B-ranked consumer method.

The unexpected-error path also referenced the parsed payload while handling errors, which made
malformed or non-object payload handling easier to regress and could mask the original failure.

## Action

Extracted focused helpers for:

- JSON object payload parsing,
- requested transaction-id normalization,
- repository-backed reprocessing execution,
- parse/retryable/unexpected error handling.

The consumer now keeps `process_message(...)` as thin orchestration around parsing, correlation
context, transaction-id validation, and repository execution. Payload validation errors are separated
from runtime `ValueError` failures so business/runtime exceptions are not mislabeled as parse
failures.

## Measured Signal

- Before: `ReprocessingConsumer.process_message(...)` was `B (6)` and the class was `B (7)`.
- After: `ReprocessingConsumer.process_message(...)` is `A (3)` and the class is `A (4)`.
- The module remains A-ranked maintainability at `A (67.65)`.

## Validation

- `python -m pytest tests\unit\services\calculators\cost_calculator_service\consumer\test_reprocessing_consumer.py -q`
  - `6 passed`
- `python -m ruff check src\services\calculators\cost_calculator_service\app\consumers\reprocessing_consumer.py tests\unit\services\calculators\cost_calculator_service\consumer\test_reprocessing_consumer.py`
  - passed
- `python -m ruff format --check src\services\calculators\cost_calculator_service\app\consumers\reprocessing_consumer.py tests\unit\services\calculators\cost_calculator_service\consumer\test_reprocessing_consumer.py`
  - passed
- `python -m radon cc src\services\calculators\cost_calculator_service\app\consumers\reprocessing_consumer.py -s`
  - target method and class are A-ranked
- `python -m radon mi src\services\calculators\cost_calculator_service\app\consumers\reprocessing_consumer.py -s`
  - module is A-ranked

## Residual Risk

This slice preserves the existing reprocessing topic, repository call, retry behavior, DLQ posture,
and correlation propagation. It does not change public APIs, OpenAPI, source-data contracts, domain
product declarations, database schema, or wiki-facing operator behavior. Documentation update is
limited to the review ledger, CR evidence note, refactor health report, and quality scorecard; no
README or wiki source change is required.
