# CR-282 Support Job Skipped State Truth

## Summary

Valuation jobs can durably end in `SKIPPED_NO_POSITION`, but the query-service support helper was
still collapsing that real outcome into `COMPLETED`.

## Finding

- Class: support-plane lifecycle truth gap
- Consequence: operators could see a skipped valuation job presented as completed, which hides a
  meaningful business outcome and weakens triage semantics on a banking control surface.

## Action Taken

- updated `OperationsService._get_support_job_operational_state(...)` to map `SKIPPED*` statuses
  to explicit operator-facing `SKIPPED`
- widened `SupportJobRecord.operational_state` to include `SKIPPED`
- added unit coverage for the helper branch
- added DB-backed integration coverage proving that a real valuation support listing exposes
  `SKIPPED_NO_POSITION` as:
  - `status == "SKIPPED_NO_POSITION"`
  - `operational_state == "SKIPPED"`
  - `is_terminal_failure == False`

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_service/test_int_operations_service.py -q`
  - `56 passed`
- `python -m ruff check src/services/query_service/app/services/operations_service.py src/services/query_service/app/dtos/operations_dto.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_service/test_int_operations_service.py`
  - passed
- `python scripts/openapi_quality_gate.py`
  - passed

## Follow-up

- keep checking support-plane derived states against durable runtime outcomes so that real
  non-failure outcomes do not get flattened into generic completed buckets
