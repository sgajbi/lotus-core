# CR-147 - Aggregation Scheduler Correlation Header Review

## Scope
- `src/services/portfolio_aggregation_service/app/core/aggregation_scheduler.py`
- `tests/unit/services/portfolio_aggregation_service/core/test_aggregation_scheduler.py`

## Finding
The portfolio aggregation scheduler always emitted a Kafka `correlation_id` header, even when the durable job carried no lineage. That produced an empty header on the wire instead of omitting the header entirely.

This was inconsistent with the normalized lineage behavior already enforced across replay, ingestion, and the valuation scheduler.

## Fix
- Emit the Kafka `correlation_id` header only when `job.correlation_id` is present.
- Add direct unit proof for:
  - lineage present -> header emitted
  - lineage absent -> header omitted

## Result
The aggregation scheduler now matches the same transport-level lineage contract as the valuation scheduler and other replay-adjacent publishers.
