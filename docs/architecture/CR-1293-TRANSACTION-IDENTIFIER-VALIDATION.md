# CR-1293 Transaction Identifier Validation Boundary

## Scope

Issue cluster: GitHub issue #702.

This slice moves required transaction identifier validation to the transaction request model
boundary so malformed transaction ingestion requests are rejected before ingestion jobs, Kafka
publish attempts, or failure bookkeeping are created.

## Objective

Reduce runtime complexity and incorrect support noise by preventing invalid transaction identity
data from entering the asynchronous ingestion workflow. Keep the publish-service partition-key
guard as defensive protection for non-API callers, but make it unreachable for normal validated API
requests.

## Changes

1. Added a shared validator on `Transaction.transaction_id`, `portfolio_id`, `instrument_id`, and
   `security_id` that trims surrounding whitespace and rejects blank values.
2. Added model tests for trimming and blank/whitespace-only rejection across all four fields.
3. Added API tests proving blank identifiers return `422` and do not create ingestion jobs, failure
   rows, Kafka publish attempts, or retry/failure mutation side effects.
4. Updated the defensive service test to bypass Pydantic intentionally with `model_construct(...)`
   so the lower-level partition-key guard remains covered for internal callers.

## Behavior And Compatibility

Valid transaction ingestion behavior is unchanged. Surrounding whitespace on the four required
identity fields is normalized before downstream publishing, matching the existing partition-key
normalization behavior.

Invalid blank/whitespace-only `transaction_id`, `portfolio_id`, `instrument_id`, and `security_id`
now fail at request validation with HTTP `422` instead of creating an ingestion job and later
failing inside publish/bookkeeping logic.

No route path, request envelope, success response DTO, Kafka topic, partition-key selection for
valid requests, ingestion job success behavior, or OpenAPI route metadata changed.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\ingestion_service\test_transaction_model.py tests\unit\services\ingestion_service\services\test_ingestion_service.py tests\integration\services\ingestion_service\test_ingestion_routers.py -k "blank_identifiers or transaction_model_trims_required_identity_fields or transaction_model_rejects_blank_required_identity_fields or empty_partition_key or trims_partition_key or ingest_transactions_endpoint"`
   - 12 passed, 242 deselected, with one expected warning from deliberate `model_construct(...)`
     invalid-object setup in the defensive service guard test.
2. `python -m ruff check src\services\ingestion_service\app\DTOs\transaction_model_dto.py tests\unit\services\ingestion_service\test_transaction_model.py tests\unit\services\ingestion_service\services\test_ingestion_service.py tests\integration\services\ingestion_service\test_ingestion_routers.py`
   - passed.
3. `python -m ruff format --check src\services\ingestion_service\app\DTOs\transaction_model_dto.py tests\unit\services\ingestion_service\test_transaction_model.py tests\unit\services\ingestion_service\services\test_ingestion_service.py tests\integration\services\ingestion_service\test_ingestion_routers.py`
   - passed after formatting.

## Documentation, Wiki, Context, And Skill Decision

No README, wiki, repo context, central context, or skill update is required. This is a narrow API
validation correctness fix with behavior fully covered in DTO and route tests.

## Remaining Work

Continue high-throughput issue fixes with the next correctness/operability families. Issue #701
needs lifecycle compare-and-set/state-transition protection; issue #700 needs a direct indexed
correlation lookup for consumer DLQ replay.
