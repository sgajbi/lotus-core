# CR-146 - Scheduler Dispatch Correlation Header Review

## Scope
- `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
- `tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`

## Finding
The valuation scheduler already carried `job.correlation_id` in the event payload, but it always emitted a Kafka header tuple for `correlation_id`, even when the value was absent. That produced an empty header on the wire instead of omitting the header entirely.

This was inconsistent with the rest of the replay and write-plane lineage normalization work, where unset lineage is represented as missing, not as a sentinel or empty value.

## Fix
- Emit the Kafka `correlation_id` header only when `job.correlation_id` is present.
- Add unit proof for both:
  - lineage present -> header emitted
  - lineage absent -> header omitted

## Result
Transport-level lineage now matches the normalized contract already enforced in the event payload and adjacent replay/ingestion boundaries.
