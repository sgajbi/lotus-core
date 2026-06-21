# CR-1145 Ingestion Retry Payload Filter Boundary

Date: 2026-06-22

## Scope

Partial ingestion retry payload filtering in
`src/services/event_replay_service/app/routers/ingestion_operations.py`.

## Finding

`_filter_payload_by_record_keys(...)` mixed endpoint dispatch, payload collection selection,
record-key extraction, business-date string normalization, transaction-id list filtering, and
unsupported endpoint posture in one C-ranked helper used by ingestion job retry.

Radon reported:

- `_filter_payload_by_record_keys`: `C (17)`

## Action Taken

Extracted focused helpers and a governed endpoint-to-filter dispatch table for:

- record collection filtering,
- record-key extraction and optional string normalization,
- transaction, portfolio, instrument, and business-date retry payloads,
- reprocess transaction-id payloads,
- unsupported partial-retry endpoint posture.

The supported endpoint set, returned payload shapes, no-record-key behavior, and unsupported
partial retry error message remain unchanged.

## Evidence

Focused unit proof:

- `python -m pytest tests\unit\services\event_replay_service\test_ingestion_operations.py -q`
- Result: `7 passed`

Focused route proof:

- `python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_partial_retry_dry_run tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_full_retry_returns_complete_job_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_retry_blocks_unsupported_partial_scope_and_paused_mode -q`
- Result: `3 passed`

Focused static proof:

- `python -m ruff check src/services/event_replay_service/app/routers/ingestion_operations.py tests/unit/services/event_replay_service/test_ingestion_operations.py`
- Result: passed

Focused format proof:

- `python -m ruff format --check src/services/event_replay_service/app/routers/ingestion_operations.py tests/unit/services/event_replay_service/test_ingestion_operations.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/event_replay_service/app/routers/ingestion_operations.py -s --exclude "*/build/*"`
- Result: `_filter_payload_by_record_keys` is `A (3)`

Measured movement:

- `_filter_payload_by_record_keys`: `C (17)` -> `A (3)`

## Residual Risk

This slice does not change ingestion retry policy, pause-mode enforcement, duplicate replay
fingerprinting, replay audit persistence, or Kafka publication behavior. The larger
`retry_ingestion_job(...)` and `replay_consumer_dlq_event(...)` route functions remain separate
measured hotspots.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of operator-triggered partial retry payload selection,
- explicit supported endpoint truth through a dispatch table,
- direct proof that unsupported partial retry remains blocked.

It does not claim full bank-buyable readiness for `lotus-core`.
