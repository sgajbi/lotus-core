# CR-1398 Ingestion Validation Error Taxonomy

## Objective

Fix GitHub issue #560 by replacing representative plain ingestion DTO `ValueError` failures with a
shared, machine-readable validation taxonomy and by carrying those codes through bulk-upload
row-level validation responses.

## Expected Improvement

- Operators and upstream systems can aggregate ingestion validation failures by stable codes.
- Repeated effective-window and duplicate-source-key validation logic now uses a shared helper.
- Bulk upload preview/commit errors preserve the existing `message` field while adding safe
  `code`, `severity`, `field_path`, `record_key`, `remediation`, and `source_lineage`.
- The change improves design modularity inside the existing ingestion service; no runtime service
  split is justified.

## Scope

Changed representative high-value DTO families:

- source-observation `quality_status`
- client tax profiles
- client tax rule sets
- sustainability preference profiles
- transaction identifier validation
- bulk upload row-error aggregation and OpenAPI schema

## Behavior And Compatibility

Public upload responses are additive and preserve `row_number` plus `message`. Existing JSON
ingestion validation messages are preserved while Pydantic validation details now include stable
error `type` values for the migrated rules.

No route path, status code, database schema, Kafka topic, event payload, or deployment topology
changed.

## Validation Evidence

- `python -m pytest tests\unit\services\ingestion_service\test_reference_data_dto.py tests\unit\services\ingestion_service\services\test_upload_validation.py tests\unit\services\ingestion_service\services\test_upload_ingestion_service.py tests\unit\services\ingestion_service\routers\test_uploads.py -q`
  - `63 passed`
- `python -m pytest tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py -k "upload_parameters_and_shared_schemas or reference_data_shared_schema" -q`
  - `2 passed, 32 deselected`
- Scoped Ruff check/fix over touched code and tests passed after automatic import formatting.

## Documentation And Guidance Decision

- Repo context updated because future ingestion DTOs should use
  `ingestion_validation_errors.py` instead of plain local `ValueError` for domain rules.
- Testing strategy and wiki source updated because upload validation error shape is public API
  contract evidence.
- No platform skill change: the repeated lesson is repository-local and already covered by
  backend delivery guidance requiring reusable patterns, tests, and repo context updates.
