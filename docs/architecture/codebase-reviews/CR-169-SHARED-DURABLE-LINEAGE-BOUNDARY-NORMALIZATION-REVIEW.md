# CR-169 Shared Durable Lineage Boundary Normalization Review

## Finding
Replay repositories were hardened in CR-168, but other shared durable repositories still accepted raw `correlation_id` values. That meant outbox rows, processed-event rows, and valuation-job rows could still persist the sentinel `"<not-set>"` if an upstream path regressed.

## Change
Normalized `correlation_id` at the repository boundary in:
- `OutboxRepository.create_outbox_event(...)`
- `IdempotencyRepository.mark_event_processed(...)`
- `ValuationJobRepository.upsert_job(...)`

Added direct unit proof for each repository.

## Outcome
Durable lineage normalization is now consistent across the shared persistence layer, not only in selected call paths.

## Evidence
- `src/libs/portfolio-common/portfolio_common/outbox_repository.py`
- `src/libs/portfolio-common/portfolio_common/idempotency_repository.py`
- `src/libs/portfolio-common/portfolio_common/valuation_job_repository.py`
- `tests/unit/libs/portfolio-common/test_outbox_repository.py`
- `tests/unit/libs/portfolio-common/test_idempotency_repository.py`
- `tests/unit/libs/portfolio-common/test_valuation_job_repository.py`
